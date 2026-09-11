"""Amazon integration API (Phase 9).

- ``POST imports/``            upload a CSV, creates a PENDING batch and
                                enqueues the import task (never inline).
- ``GET imports/``             import history.
- ``GET imports/{id}/``        one batch -- poll ``status`` for
                                PENDING/PROCESSING -> READY/PARTIAL/FAILED.
- ``sku-mappings/``             CRUD -- Amazon SKU <-> Hexagare variant.
- ``fee-config/``                CRUD -- the configurable fee structure
                                (HEXAGARE_FEATURES.md section 22).
- ``settlements/``              read-only -- per-line Amazon financials
                                (``?sale=``).

Everything here is gated by the single ``integrations.amazon`` operational
permission (reserved since Phase 1's rbac.py) -- "Import Amazon orders and
manage Amazon settings" already reads as one combined capability.
"""

from __future__ import annotations

from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from apps.accounts.permissions import require

from .models import AmazonFeeConfig, AmazonImportBatch, AmazonOrderSettlement, AmazonSkuMapping
from .serializers import (
    AmazonFeeConfigSerializer,
    AmazonImportBatchCreateSerializer,
    AmazonImportBatchDetailSerializer,
    AmazonImportBatchListSerializer,
    AmazonOrderSettlementSerializer,
    AmazonSkuMappingSerializer,
)
from .tasks import import_amazon_orders

_PERM = "integrations.amazon"


class AmazonImportBatchViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    http_method_names = ["get", "post", "head", "options"]
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at", "status"]

    def get_permissions(self):
        return [require(_PERM)()]

    def get_queryset(self):
        return AmazonImportBatch.objects.select_related("created_by").order_by(
            "-created_at", "-id"
        )

    def get_serializer_class(self):
        return {
            "list": AmazonImportBatchListSerializer,
            "create": AmazonImportBatchCreateSerializer,
        }.get(self.action, AmazonImportBatchDetailSerializer)

    @extend_schema(
        request=AmazonImportBatchCreateSerializer, responses=AmazonImportBatchDetailSerializer
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = request.user if getattr(request.user, "is_authenticated", False) else None
        batch = serializer.save(created_by=actor)

        transaction.on_commit(lambda: import_amazon_orders.delay(batch.pk))

        detail = AmazonImportBatchDetailSerializer(batch, context=self.get_serializer_context())
        return Response(detail.data, status=201)


class AmazonSkuMappingViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    serializer_class = AmazonSkuMappingSerializer
    filter_backends = [OrderingFilter]
    ordering_fields = ["amazon_sku", "created_at"]

    def get_permissions(self):
        return [require(_PERM)()]

    def get_queryset(self):
        qs = AmazonSkuMapping.objects.select_related("variant__product").order_by("amazon_sku")
        if search := self.request.query_params.get("search"):
            qs = qs.filter(amazon_sku__icontains=search)
        return qs


class AmazonFeeConfigViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    serializer_class = AmazonFeeConfigSerializer
    filter_backends = [OrderingFilter]
    ordering_fields = ["fee_name", "effective_from"]

    def get_permissions(self):
        return [require(_PERM)()]

    def get_queryset(self):
        qs = AmazonFeeConfig.objects.select_related(
            "sales_channel", "applicable_category", "applicable_product"
        )
        if fee_name := self.request.query_params.get("fee_name"):
            qs = qs.filter(fee_name=fee_name)
        return qs


class AmazonOrderSettlementViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = AmazonOrderSettlementSerializer
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at"]

    def get_permissions(self):
        return [require(_PERM)()]

    @extend_schema(parameters=[OpenApiParameter("sale", int)])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = AmazonOrderSettlement.objects.select_related("sale", "variant__product")
        if sale := self.request.query_params.get("sale"):
            qs = qs.filter(sale_id=sale)
        return qs
