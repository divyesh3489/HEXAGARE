"""Catalog API viewsets.

Every viewset gates per action via ``get_permissions()``: reads need
``products.view``, writes need ``products.manage`` (see ``apps.accounts.rbac``).
"""

from __future__ import annotations

from django.db.models import Count, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import require

from .models import (
    Category,
    LabelSize,
    Product,
    ProductAttribute,
    ProductImage,
    ProductVariant,
)
from .serializers import (
    CategorySerializer,
    LabelSizeSerializer,
    ProductAttributeSerializer,
    ProductDetailSerializer,
    ProductImageSerializer,
    ProductListSerializer,
    ProductVariantSerializer,
    SkuSuggestionSerializer,
)
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


class ProductViewSet(_CatalogPermissionMixin, viewsets.ModelViewSet):
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "brand", "code", "variants__sku"]
    ordering_fields = ["name", "updated_at", "status"]

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


class ProductVariantViewSet(_CatalogPermissionMixin, viewsets.ModelViewSet):
    serializer_class = ProductVariantSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["sku", "name", "barcode"]
    ordering_fields = ["sku", "selling_price", "created_at"]

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
