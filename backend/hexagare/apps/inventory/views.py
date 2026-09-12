"""Inventory API (Phase 4 ledger).

- ``locations/``      -- CRUD. Reads ``inventory.view``; writes ``stock_adjustments``.
- ``balances/``       -- read-only balance cache (``inventory.view``).
- ``transactions/``   -- read-only stock ledger (``inventory.view``).
- ``policies/``       -- min/max stock-level policies. Reads ``inventory.view``;
                         writes ``stock_adjustments``.
- ``transfers/``      -- scan-based stock transfers (``inventory.transfer``).
- ``overview/``       -- stock by variant x location x status, computed live from
                         the serialized units (``inventory.view``).
- ``alerts/``         -- low / out / overstock + cache-mismatch (``inventory.view``).
- ``adjustments/``    -- manual non-serialized quantity correction (``stock_adjustments``).
"""

from __future__ import annotations

from django.db import models, transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.audit import AuditMixin
from apps.accounts.models import AuditLogEntry
from apps.accounts.permissions import require
from apps.products.models import SerializedUnit
from apps.products.services.serialized_inventory import SerializedInventoryService

from .models import (
    InventoryBalance,
    InventoryTransaction,
    Location,
    StockLevelPolicy,
    StockTransfer,
    StockTransferLine,
)
from .serializers import (
    InventoryAdjustmentSerializer,
    InventoryAlertSerializer,
    InventoryBalanceSerializer,
    InventoryOverviewSerializer,
    InventoryTransactionSerializer,
    LocationSerializer,
    StockLevelPolicySerializer,
    StockTransferScanSerializer,
    StockTransferSerializer,
)
from .services.alerts import compute_alerts
from .services.ledger import InventoryService

_VIEW = "inventory.view"
_ADJUST = "stock_adjustments"
_TRANSFER = "inventory.transfer"
_READ_ACTIONS = {"list", "retrieve"}


def _truthy(value: str) -> bool:
    return value.lower() in {"1", "true", "yes"}


class LocationViewSet(AuditMixin, viewsets.ModelViewSet):
    """List / retrieve / create / update / delete stock locations."""

    serializer_class = LocationSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "code"]
    ordering_fields = ["name", "created_at"]

    audit_created_action = AuditLogEntry.Action.LOCATION_CREATED
    audit_updated_action = AuditLogEntry.Action.LOCATION_UPDATED
    audit_deleted_action = AuditLogEntry.Action.LOCATION_DELETED

    def get_permissions(self):
        codename = _VIEW if self.action in _READ_ACTIONS else _ADJUST
        return [require(codename)()]

    def get_queryset(self):
        qs = Location.objects.all()
        params = self.request.query_params
        if (kind := params.get("kind")) is not None:
            qs = qs.filter(kind=kind)
        if (is_active := params.get("is_active")) is not None:
            qs = qs.filter(is_active=_truthy(is_active))
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("kind", str),
            OpenApiParameter("is_active", bool),
            OpenApiParameter("search", str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def perform_destroy(self, instance):
        if instance.serialized_units.exists() or instance.inventory_balances.exists():
            raise ValidationError(
                "This location still holds stock or unit history and cannot be deleted. "
                "Deactivate it instead."
            )
        # Resolves to AuditMixin.perform_destroy next in the MRO, which logs
        # audit_deleted_action after the actual delete.
        super().perform_destroy(instance)


class InventoryBalanceViewSet(viewsets.ReadOnlyModelViewSet):
    """The rebuildable on-hand cache. One row per (variant, location, status)."""

    serializer_class = InventoryBalanceSerializer
    permission_classes = [require(_VIEW)]
    filter_backends = [OrderingFilter]
    ordering_fields = ["quantity", "updated_at"]

    def get_queryset(self):
        qs = InventoryBalance.objects.select_related("variant__product", "location")
        params = self.request.query_params
        if variant := params.get("variant"):
            qs = qs.filter(variant_id=variant)
        if location := params.get("location"):
            qs = qs.filter(location_id=location)
        if status_ := params.get("status"):
            qs = qs.filter(status=status_)
        if product := params.get("product"):
            qs = qs.filter(variant__product_id=product)
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("variant", int),
            OpenApiParameter("location", int),
            OpenApiParameter("status", str),
            OpenApiParameter("product", int),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class InventoryTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """The immutable stock ledger. Every balance change is one row."""

    serializer_class = InventoryTransactionSerializer
    permission_classes = [require(_VIEW)]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["serialized_unit__serial_number", "note"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        qs = InventoryTransaction.objects.select_related(
            "variant__product", "location", "serialized_unit", "actor"
        )
        params = self.request.query_params
        if variant := params.get("variant"):
            qs = qs.filter(variant_id=variant)
        if location := params.get("location"):
            qs = qs.filter(location_id=location)
        if status_ := params.get("status"):
            qs = qs.filter(status=status_)
        if kind := params.get("kind"):
            qs = qs.filter(kind=kind)
        if reference := params.get("reference"):
            qs = qs.filter(reference=reference)
        if unit := params.get("serialized_unit"):
            qs = qs.filter(serialized_unit_id=unit)
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("variant", int),
            OpenApiParameter("location", int),
            OpenApiParameter("status", str),
            OpenApiParameter("kind", str),
            OpenApiParameter("reference", str),
            OpenApiParameter("serialized_unit", int),
            OpenApiParameter("search", str),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class StockLevelPolicyViewSet(viewsets.ModelViewSet):
    """Min / max on-hand thresholds that drive the alerts."""

    serializer_class = StockLevelPolicySerializer
    filter_backends = [OrderingFilter]
    ordering_fields = ["min_quantity", "max_quantity", "updated_at"]

    def get_permissions(self):
        codename = _VIEW if self.action in _READ_ACTIONS else _ADJUST
        return [require(codename)()]

    def get_queryset(self):
        qs = StockLevelPolicy.objects.select_related("variant__product", "location")
        params = self.request.query_params
        if variant := params.get("variant"):
            qs = qs.filter(variant_id=variant)
        if location := params.get("location"):
            qs = qs.filter(location_id=location)
        if (is_active := params.get("is_active")) is not None:
            qs = qs.filter(is_active=_truthy(is_active))
        return qs


class StockTransferViewSet(viewsets.ModelViewSet):
    """Scan-based movement of serialized units between two locations.

    ``POST``                      create an OPEN transfer (from_location, to_location, note)
    ``POST {id}/scan/``           add one unit by serial (AVAILABLE -> IN_TRANSIT + ledger)
    ``POST {id}/receive/``        complete it (each line IN_TRANSIT -> AVAILABLE @ to_location)
    ``POST {id}/cancel/``         roll every line back to AVAILABLE @ from_location
    """

    serializer_class = StockTransferSerializer
    permission_classes = [require(_TRANSFER)]
    http_method_names = ["get", "post", "head", "options"]
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at", "status"]

    def get_queryset(self):
        qs = StockTransfer.objects.select_related(
            "from_location", "to_location", "created_by"
        ).prefetch_related(
            "lines__serialized_unit__variant__product",
        )
        params = self.request.query_params
        if status_ := params.get("status"):
            qs = qs.filter(status=status_)
        if location := params.get("location"):
            qs = qs.filter(models.Q(from_location_id=location) | models.Q(to_location_id=location))
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def _detail_response(self, transfer, status_code=200):
        transfer = self.get_queryset().get(pk=transfer.pk)
        return Response(
            StockTransferSerializer(transfer, context=self.get_serializer_context()).data,
            status=status_code,
        )

    @extend_schema(request=StockTransferScanSerializer, responses=StockTransferSerializer)
    @action(detail=True, methods=["post"])
    def scan(self, request, pk=None):
        transfer = self.get_object()
        serializer = StockTransferScanSerializer(
            data=request.data,
            context={**self.get_serializer_context(), "transfer": transfer},
        )
        serializer.is_valid(raise_exception=True)
        unit = serializer.context["unit"]
        with transaction.atomic():
            SerializedInventoryService.start_transfer(
                unit, actor=request.user, note=f"transfer #{transfer.pk}"
            )
            StockTransferLine.objects.create(transfer=transfer, serialized_unit=unit)
        return self._detail_response(transfer, status_code=201)

    @extend_schema(request=None, responses=StockTransferSerializer)
    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != StockTransfer.Status.OPEN:
            raise ValidationError("Only an open transfer can be received.")
        with transaction.atomic():
            lines = transfer.lines.select_related("serialized_unit").filter(received=False)
            for line in lines:
                SerializedInventoryService.complete_transfer(
                    line.serialized_unit,
                    to_location=transfer.to_location,
                    actor=request.user,
                    note=f"transfer #{transfer.pk}",
                )
                line.received = True
                line.save(update_fields=["received"])
            transfer.status = StockTransfer.Status.COMPLETED
            transfer.completed_at = timezone.now()
            transfer.save(update_fields=["status", "completed_at", "updated_at"])
        return self._detail_response(transfer)

    @extend_schema(request=None, responses=StockTransferSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != StockTransfer.Status.OPEN:
            raise ValidationError("Only an open transfer can be cancelled.")
        with transaction.atomic():
            lines = transfer.lines.select_related("serialized_unit").filter(received=False)
            for line in lines:
                SerializedInventoryService.cancel_transfer(
                    line.serialized_unit,
                    actor=request.user,
                    note=f"transfer #{transfer.pk} cancelled",
                )
            transfer.status = StockTransfer.Status.CANCELLED
            transfer.save(update_fields=["status", "updated_at"])
        return self._detail_response(transfer)


class InventoryOverviewView(APIView):
    """Stock by variant x location x status, computed **live** from the
    serialized units (never from a stored counter). ``cache_matches`` flags
    whether the balance cache currently agrees."""

    permission_classes = [require(_VIEW)]

    @extend_schema(
        parameters=[
            OpenApiParameter("variant", int),
            OpenApiParameter("location", int),
            OpenApiParameter("product", int),
        ],
        responses=InventoryOverviewSerializer,
    )
    def get(self, request):
        units = SerializedUnit.objects.select_related("variant__product", "location")
        balances = InventoryBalance.objects.all()
        params = request.query_params
        if variant := params.get("variant"):
            units = units.filter(variant_id=variant)
            balances = balances.filter(variant_id=variant)
        if location := params.get("location"):
            units = units.filter(location_id=location)
            balances = balances.filter(location_id=location)
        if product := params.get("product"):
            units = units.filter(variant__product_id=product)
            balances = balances.filter(variant__product_id=product)

        grouped = (
            units.values(
                "variant_id",
                "variant__sku",
                "variant__product_id",
                "variant__product__name",
                "location_id",
                "location__name",
                "status",
            )
            .order_by("variant__sku", "location__name", "status")
            .annotate(quantity=models.Count("id"))
        )
        rows = [
            {
                "variant": row["variant_id"],
                "sku": row["variant__sku"],
                "product_id": row["variant__product_id"],
                "product_name": row["variant__product__name"],
                "location": row["location_id"],
                "location_name": row["location__name"],
                "status": row["status"],
                "quantity": row["quantity"],
            }
            for row in grouped
        ]

        totals: dict[str, int] = {}
        for row in rows:
            totals[row["status"]] = totals.get(row["status"], 0) + row["quantity"]

        live = {(r["variant"], r["location"], r["status"]): r["quantity"] for r in rows}
        cached = {
            (b.variant_id, b.location_id, b.status): b.quantity
            for b in balances
        }
        cache_matches = live == {k: v for k, v in cached.items() if v}

        return Response(
            {
                "computed_from": "serialized_units",
                "rows": rows,
                "totals_by_status": totals,
                "cache_matches": cache_matches,
            }
        )


class InventoryAlertsView(APIView):
    """Low-stock / out-of-stock / overstock (from ``StockLevelPolicy``) plus
    balance-cache mismatches."""

    permission_classes = [require(_VIEW)]

    @extend_schema(
        parameters=[
            OpenApiParameter("variant", int),
            OpenApiParameter("location", int),
            OpenApiParameter(
                "reconcile", bool, description="Include balance_mismatch alerts (default true)."
            ),
        ],
        responses=InventoryAlertSerializer(many=True),
    )
    def get(self, request):
        params = request.query_params
        reconcile = params.get("reconcile")
        alerts = compute_alerts(
            variant_id=params.get("variant") or None,
            location_id=params.get("location") or None,
            include_reconciliation=reconcile is None or _truthy(reconcile),
        )
        return Response(alerts)


class InventoryAdjustmentView(APIView):
    """Manual, non-serialized quantity correction. One ledger row + balance update."""

    permission_classes = [require(_ADJUST)]

    @extend_schema(request=InventoryAdjustmentSerializer, responses=InventoryTransactionSerializer)
    def post(self, request):
        serializer = InventoryAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        txn = InventoryService.adjust(
            variant=data["variant"],
            location=data["location"],
            status=data["status"],
            quantity=data["quantity"],
            note=data.get("note", ""),
            actor=request.user,
        )
        return Response(
            InventoryTransactionSerializer(txn).data,
            status=201,
        )
