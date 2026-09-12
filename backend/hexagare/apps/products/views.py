"""Catalog API viewsets.

Every viewset gates per action via ``get_permissions()``: reads need
``products.view``, writes need ``products.manage`` (see ``apps.accounts.rbac``).
"""

from __future__ import annotations

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.audit import AuditMixin
from apps.accounts.models import AuditLogEntry
from apps.accounts.permissions import require
from apps.common.renderers import BinaryRenderer

from .models import (
    Category,
    LabelBatch,
    LabelSize,
    Product,
    ProductAttribute,
    ProductImage,
    ProductVariant,
    SerializedUnit,
)
from .serializers import (
    CategorySerializer,
    LabelBatchCreateSerializer,
    LabelBatchDetailSerializer,
    LabelBatchSerializer,
    LabelSizeSerializer,
    NextSerialSerializer,
    ProductAttributeSerializer,
    ProductDetailSerializer,
    ProductImageSerializer,
    ProductListSerializer,
    ProductVariantSerializer,
    SerializedUnitCreateSerializer,
    SerializedUnitDetailSerializer,
    SerializedUnitListSerializer,
    SerializedUnitTransitionSerializer,
    SkuSuggestionSerializer,
)
from .services.barcodes import render_code128_png
from .services.bulk_generate import enqueue_render, next_serial_preview
from .services.serial_numbers import resolve_unit
from .services.sku import is_sku_available

_VIEW = "products.view"
_MANAGE = "products.manage"
_READ_ACTIONS = {"list", "retrieve"}


class _CatalogPermissionMixin:
    """`products.view` for reads, `products.manage` for everything else."""

    def get_permissions(self):
        codename = _VIEW if self.action in _READ_ACTIONS else _MANAGE
        return [require(codename)()]


class CategoryViewSet(_CatalogPermissionMixin, viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "code"]
    ordering_fields = ["name", "created_at"]

    def get_queryset(self):
        qs = Category.objects.select_related("parent").all()
        params = self.request.query_params
        if (parent := params.get("parent")) is not None:
            qs = qs.filter(parent__isnull=True) if parent == "" else qs.filter(parent_id=parent)
        if (is_active := params.get("is_active")) is not None:
            qs = qs.filter(is_active=is_active.lower() in {"1", "true", "yes"})
        return qs


class ProductViewSet(_CatalogPermissionMixin, AuditMixin, viewsets.ModelViewSet):
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "brand", "code", "variants__sku"]
    ordering_fields = ["name", "updated_at", "status"]

    audit_created_action = AuditLogEntry.Action.PRODUCT_CREATED
    audit_updated_action = AuditLogEntry.Action.PRODUCT_UPDATED
    audit_deleted_action = AuditLogEntry.Action.PRODUCT_DELETED

    def get_serializer_class(self):
        return ProductListSerializer if self.action == "list" else ProductDetailSerializer

    def get_queryset(self):
        qs = (
            Product.objects.select_related("category")
            .prefetch_related("variants", "variants__attribute_values__attribute", "images")
        )
        params = self.request.query_params
        if category := params.get("category"):
            qs = qs.filter(category_id=category)
        if status_ := params.get("status"):
            qs = qs.filter(status=status_)
        if brand := params.get("brand"):
            qs = qs.filter(brand__iexact=brand)
        if self.action == "list":
            qs = qs.annotate(variant_count=Count("variants", distinct=True))
        return qs.distinct().order_by("name", "id")

    @extend_schema(
        parameters=[
            OpenApiParameter("category", int),
            OpenApiParameter("status", str),
            OpenApiParameter("brand", str),
            OpenApiParameter("search", str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class ProductVariantViewSet(_CatalogPermissionMixin, AuditMixin, viewsets.ModelViewSet):
    serializer_class = ProductVariantSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["sku", "name", "barcode"]
    ordering_fields = ["sku", "selling_price", "created_at"]

    # Variant creation/edits also cover SKU + price changes (section 53) --
    # both are plain fields on this model, picked up by the generic diff.
    audit_created_action = AuditLogEntry.Action.PRODUCT_CREATED
    audit_updated_action = AuditLogEntry.Action.PRODUCT_UPDATED
    audit_deleted_action = AuditLogEntry.Action.PRODUCT_DELETED

    def get_queryset(self):
        qs = ProductVariant.objects.select_related("product").prefetch_related(
            "attribute_values__attribute"
        )
        params = self.request.query_params
        if product := params.get("product"):
            qs = qs.filter(product_id=product)
        if (is_active := params.get("is_active")) is not None:
            qs = qs.filter(is_active=is_active.lower() in {"1", "true", "yes"})
        if (available := params.get("available")) is not None:
            # "available" = sellable right now: product active AND variant active.
            sellable = Q(product__status=Product.Status.ACTIVE, is_active=True)
            qs = qs.filter(sellable) if available.lower() in {"1", "true", "yes"} else qs.exclude(
                sellable
            )
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("product", int),
            OpenApiParameter("available", bool),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class ProductAttributeViewSet(_CatalogPermissionMixin, viewsets.ModelViewSet):
    serializer_class = ProductAttributeSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "code"]
    ordering_fields = ["name"]

    def get_queryset(self):
        qs = ProductAttribute.objects.all()
        if (is_active := self.request.query_params.get("is_active")) is not None:
            qs = qs.filter(is_active=is_active.lower() in {"1", "true", "yes"})
        return qs


class ProductImageViewSet(_CatalogPermissionMixin, viewsets.ModelViewSet):
    serializer_class = ProductImageSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = ProductImage.objects.select_related("product", "variant")
        params = self.request.query_params
        if product := params.get("product"):
            qs = qs.filter(product_id=product)
        if variant := params.get("variant"):
            qs = qs.filter(variant_id=variant)
        return qs


class LabelSizeViewSet(_CatalogPermissionMixin, viewsets.ModelViewSet):
    serializer_class = LabelSizeSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "code"]
    ordering_fields = ["name"]

    def get_queryset(self):
        qs = LabelSize.objects.all()
        if (is_active := self.request.query_params.get("is_active")) is not None:
            qs = qs.filter(is_active=is_active.lower() in {"1", "true", "yes"})
        return qs


class SkuSuggestionView(APIView):
    """Suggest an available SKU for a would-be variant."""

    permission_classes = [require(_MANAGE)]
    serializer_class = SkuSuggestionSerializer

    @extend_schema(
        request=SkuSuggestionSerializer,
        responses={
            200: inline_serializer("SkuSuggestionResult", {"sku": serializers.CharField()})
        },
    )
    def post(self, request):
        serializer = SkuSuggestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"sku": serializer.suggest()})


class SkuAvailabilityView(APIView):
    """Check whether a SKU string is free."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter("sku", str, required=True),
            OpenApiParameter("exclude_variant", int),
        ],
        responses={
            200: inline_serializer(
                "SkuAvailability",
                {"sku": serializers.CharField(), "available": serializers.BooleanField()},
            )
        },
    )
    def get(self, request):
        sku = request.query_params.get("sku", "").strip()
        if not sku:
            raise serializers.ValidationError({"sku": "This query parameter is required."})
        exclude = request.query_params.get("exclude_variant")
        available = is_sku_available(
            sku, exclude_variant_id=int(exclude) if exclude else None
        )
        return Response({"sku": sku, "available": available})


class BarcodePNGRenderer(BinaryRenderer):
    """Streams the on-demand Code128 PNG straight through."""

    media_type = "image/png"
    format = "png"


class SerializedUnitViewSet(viewsets.ModelViewSet):
    """Serialized units: list / retrieve / create one, transition status,
    render the on-demand barcode, and resolve a scanned serial to the full
    chain (rule 4).

    Reads need ``serials.view``; create / transition need ``serials.manage``;
    ``lookup`` needs ``barcode.scan``.
    """

    # No PUT/PATCH/DELETE -- serials are immutable and status moves only via
    # ``transition`` (Phase 3) or ``SerializedInventoryService`` (Phase 4+).
    http_method_names = ["get", "post", "head", "options"]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["serial_number"]
    ordering_fields = ["created_at", "serial_number", "status"]

    def get_permissions(self):
        if self.action in {"list", "retrieve", "barcode"}:
            return [require("serials.view")()]
        if self.action == "lookup":
            return [require("barcode.scan")()]
        return [require("serials.manage")()]

    def get_queryset(self):
        qs = SerializedUnit.objects.select_related(
            "variant__product__category", "location"
        )
        if self.action == "retrieve":
            qs = qs.prefetch_related("events__location", "events__actor")
        params = self.request.query_params
        if status_ := params.get("status"):
            qs = qs.filter(status=status_)
        if location := params.get("location"):
            qs = qs.filter(location_id=location)
        if variant := params.get("variant"):
            qs = qs.filter(variant_id=variant)
        if product := params.get("product"):
            qs = qs.filter(variant__product_id=product)
        return qs

    def get_serializer_class(self):
        return {
            "list": SerializedUnitListSerializer,
            "create": SerializedUnitCreateSerializer,
            "transition": SerializedUnitTransitionSerializer,
        }.get(self.action, SerializedUnitDetailSerializer)

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str),
            OpenApiParameter("location", int),
            OpenApiParameter("variant", int),
            OpenApiParameter("product", int),
            OpenApiParameter("search", str, description="Serial number (contains)."),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=SerializedUnitTransitionSerializer,
        responses=SerializedUnitDetailSerializer,
    )
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        unit = self.get_object()
        serializer = SerializedUnitTransitionSerializer(
            data=request.data,
            context={**self.get_serializer_context(), "unit": unit},
        )
        serializer.is_valid(raise_exception=True)
        unit = serializer.save()
        return Response(
            SerializedUnitDetailSerializer(
                unit, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], renderer_classes=[BarcodePNGRenderer])
    def barcode(self, request, pk=None):
        unit = self.get_object()
        return Response(
            render_code128_png(unit.serial_number), content_type="image/png"
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "code",
                str,
                required=True,
                description="Serial number or scanned barcode value.",
            )
        ],
        responses=SerializedUnitDetailSerializer,
    )
    @action(detail=False, methods=["get"])
    def lookup(self, request):
        unit = resolve_unit(request.query_params.get("code", ""))
        return Response(
            SerializedUnitDetailSerializer(
                unit, context=self.get_serializer_context()
            ).data
        )


class LabelBatchPDFRenderer(BinaryRenderer):
    """Streams a batch's rendered label sheet."""

    media_type = "application/pdf"
    format = "pdf"


class LabelBatchViewSet(viewsets.ModelViewSet):
    """Bulk unit generation + label-sheet PDFs (Phase 5).

    ``POST``                    generate N units of a variant + their label batch
                                (all-or-nothing); the PDF renders async.
    ``GET``                     generation history.
    ``GET {id}/``               one batch -- poll ``status`` for PENDING -> READY.
    ``POST {id}/regenerate/``   re-render the PDF (units untouched).
    ``GET {id}/pdf/``           download the rendered sheet (when READY).
    ``GET next-serial/?variant= `` preview the serial the next allocation yields.

    Reads need ``serials.view``; generate / regenerate need ``serials.manage``.
    """

    http_method_names = ["get", "post", "head", "options"]
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at", "status", "quantity"]

    def get_permissions(self):
        if self.action in {"create", "regenerate"}:
            return [require("serials.manage")()]
        return [require("serials.view")()]

    def get_queryset(self):
        qs = (
            LabelBatch.objects.select_related(
                "variant__product", "location", "label_size", "created_by"
            )
            .annotate(unit_count=Count("items", distinct=True))
            .order_by("-created_at", "-id")
        )
        params = self.request.query_params
        if variant := params.get("variant"):
            qs = qs.filter(variant_id=variant)
        if product := params.get("product"):
            qs = qs.filter(variant__product_id=product)
        if status_ := params.get("status"):
            qs = qs.filter(status=status_)
        if location := params.get("location"):
            qs = qs.filter(location_id=location)
        return qs

    def get_serializer_class(self):
        return {
            "list": LabelBatchSerializer,
            "create": LabelBatchCreateSerializer,
        }.get(self.action, LabelBatchDetailSerializer)

    def _detail_data(self, batch):
        batch = self.get_queryset().get(pk=batch.pk)
        return LabelBatchDetailSerializer(
            batch, context=self.get_serializer_context()
        ).data

    @extend_schema(
        parameters=[
            OpenApiParameter("variant", int),
            OpenApiParameter("product", int),
            OpenApiParameter("location", int),
            OpenApiParameter("status", str),
        ],
        responses=LabelBatchSerializer,
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request=LabelBatchCreateSerializer, responses=LabelBatchDetailSerializer
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch = serializer.save()
        return Response(self._detail_data(batch), status=201)

    @extend_schema(request=None, responses=LabelBatchDetailSerializer)
    @action(detail=True, methods=["post"])
    def regenerate(self, request, pk=None):
        batch = self.get_object()
        enqueue_render(batch)
        return Response(self._detail_data(batch))

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], renderer_classes=[LabelBatchPDFRenderer])
    def pdf(self, request, pk=None):
        batch = self.get_object()
        if batch.status != LabelBatch.Status.READY or not batch.pdf_file:
            raise serializers.ValidationError(
                "The label PDF for this batch is not ready yet."
            )
        with batch.pdf_file.open("rb") as handle:
            data = handle.read()
        return Response(data, content_type="application/pdf")

    @extend_schema(
        parameters=[OpenApiParameter("variant", int, required=True)],
        responses=NextSerialSerializer,
    )
    @action(detail=False, methods=["get"], url_path="next-serial")
    def next_serial(self, request):
        variant_id = request.query_params.get("variant")
        if not variant_id:
            raise serializers.ValidationError(
                {"variant": "This query parameter is required."}
            )
        variant = get_object_or_404(ProductVariant, pk=variant_id)
        return Response(next_serial_preview(variant))
