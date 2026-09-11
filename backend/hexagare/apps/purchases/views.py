"""Purchases API (Phase 12).

- ``orders/``                           list/retrieve (``purchases.view``);
                                         create (``purchases.manage``)
- ``orders/{id}/lines/``                POST   add a line (only while DRAFT)
- ``orders/{id}/lines/{line_id}/``      PATCH  edit a line / DELETE remove it
- ``orders/{id}/place/``                POST   DRAFT -> ORDERED
- ``orders/{id}/receive/``              POST   receive stock (``purchases_receiving``)
- ``orders/{id}/payments/``             POST   record a payment/refund
- ``orders/{id}/cancel/``               POST   cancel the order
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import require

from .models import PurchaseOrder, PurchaseOrderLine
from .serializers import (
    PurchaseOrderCreateSerializer,
    PurchaseOrderDetailSerializer,
    PurchaseOrderLineUpdateSerializer,
    PurchaseOrderLineWriteSerializer,
    PurchaseOrderListSerializer,
    PurchaseOrderPaymentWriteSerializer,
    ReceiveStockSerializer,
)
from .services import PurchaseTotalsService, ReceiveStockService

_VIEW = "purchases.view"
_MANAGE = "purchases.manage"
_RECEIVE = "purchases_receiving"


class PurchaseOrderViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Deliberately excludes ``UpdateModelMixin``/``DestroyModelMixin`` -- an
    order is only ever changed via the actions below, and is never hard-deleted."""

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [require(_VIEW)()]
        if self.action == "receive":
            return [require(_RECEIVE)()]
        return [require(_MANAGE)()]

    def get_serializer_class(self):
        if self.action == "list":
            return PurchaseOrderListSerializer
        if self.action == "create":
            return PurchaseOrderCreateSerializer
        return PurchaseOrderDetailSerializer

    def get_queryset(self):
        qs = PurchaseOrder.objects.select_related("supplier").prefetch_related(
            "lines__variant__product", "lines__units__serialized_unit", "payments"
        )
        params = self.request.query_params
        if supplier := params.get("supplier"):
            qs = qs.filter(supplier_id=supplier)
        if status_ := params.get("status"):
            qs = qs.filter(status=status_)
        return qs

    def _detail_response(self, purchase_order: PurchaseOrder, status_code: int = 200) -> Response:
        purchase_order = self.get_queryset().get(pk=purchase_order.pk)
        return Response(
            PurchaseOrderDetailSerializer(
                purchase_order, context=self.get_serializer_context()
            ).data,
            status=status_code,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        purchase_order = serializer.save()
        return self._detail_response(purchase_order, status_code=201)

    def _editable_order(self, pk) -> PurchaseOrder:
        purchase_order = get_object_or_404(PurchaseOrder, pk=pk)
        if not purchase_order.is_editable:
            raise ValidationError(
                f"Purchase order is {purchase_order.status} -- its lines can no longer be edited."
            )
        return purchase_order

    @extend_schema(
        request=PurchaseOrderLineWriteSerializer, responses=PurchaseOrderDetailSerializer
    )
    @action(detail=True, methods=["post"], url_path="lines")
    def add_line(self, request, pk=None):
        purchase_order = self._editable_order(pk)
        serializer = PurchaseOrderLineWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.create_line(purchase_order)
        PurchaseTotalsService.recalculate(purchase_order)
        return self._detail_response(purchase_order)

    @extend_schema(
        request=PurchaseOrderLineUpdateSerializer, responses=PurchaseOrderDetailSerializer
    )
    @action(detail=True, methods=["patch", "delete"], url_path=r"lines/(?P<line_id>[^/.]+)")
    def line_detail(self, request, pk=None, line_id=None):
        purchase_order = self._editable_order(pk)
        line = get_object_or_404(PurchaseOrderLine, pk=line_id, purchase_order=purchase_order)
        if request.method == "DELETE":
            line.delete()
        else:
            serializer = PurchaseOrderLineUpdateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.apply(line)
        PurchaseTotalsService.recalculate(purchase_order)
        return self._detail_response(purchase_order)

    @extend_schema(request=None, responses=PurchaseOrderDetailSerializer)
    @action(detail=True, methods=["post"])
    def place(self, request, pk=None):
        purchase_order = get_object_or_404(PurchaseOrder, pk=pk)
        if purchase_order.status != PurchaseOrder.Status.DRAFT:
            raise ValidationError(
                f"Purchase order is {purchase_order.status} -- it is already placed."
            )
        if not purchase_order.lines.exists():
            raise ValidationError("Add at least one line before placing the order.")
        purchase_order.status = PurchaseOrder.Status.ORDERED
        purchase_order.save(update_fields=["status", "updated_at"])
        return self._detail_response(purchase_order)

    @extend_schema(request=ReceiveStockSerializer, responses=PurchaseOrderDetailSerializer)
    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        purchase_order = get_object_or_404(PurchaseOrder, pk=pk)
        serializer = ReceiveStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ReceiveStockService.receive(
            purchase_order,
            receipts=serializer.validated_data["receipts"],
            actor=request.user,
        )
        return self._detail_response(purchase_order)

    @extend_schema(
        request=PurchaseOrderPaymentWriteSerializer, responses=PurchaseOrderDetailSerializer
    )
    @action(detail=True, methods=["post"])
    def payments(self, request, pk=None):
        purchase_order = get_object_or_404(PurchaseOrder, pk=pk)
        serializer = PurchaseOrderPaymentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = request.user
        serializer.save(
            purchase_order=purchase_order,
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
        )
        return self._detail_response(purchase_order)

    @extend_schema(request=None, responses=PurchaseOrderDetailSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        purchase_order = get_object_or_404(PurchaseOrder, pk=pk)
        if purchase_order.status not in PurchaseOrder.CANCELLABLE_STATUSES:
            raise ValidationError(
                f"Purchase order is {purchase_order.status} -- it cannot be cancelled."
            )
        purchase_order.status = PurchaseOrder.Status.CANCELLED
        purchase_order.save(update_fields=["status", "updated_at"])
        return self._detail_response(purchase_order)
