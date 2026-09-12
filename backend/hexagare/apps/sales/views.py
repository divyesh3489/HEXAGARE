"""Sales API (Phase 7 core).

- ``channels/``  -- read-only list of sales channels (``sales.view``).
- ``sales/``     -- list/retrieve orders (``sales.view``); create/cancel and
                    line mutations (``orders.manage``).
- ``sales/{id}/lines/``              POST   add a line (only while DRAFT)
- ``sales/{id}/lines/{line_id}/``    PATCH  edit quantity / discount
- ``sales/{id}/lines/{line_id}/``    DELETE remove the line
- ``sales/{id}/units/``              POST   scan/search-add one exact unit (Phase 8)
- ``sales/{id}/units/{unit_id}/``    DELETE release/unbind one exact unit (Phase 8)
- ``sales/{id}/customer/``           POST   attach/change/clear the customer (Phase 11)
- ``sales/{id}/cancel/``             POST   cancel the sale (releases any bound units)
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.audit import log_activity
from apps.accounts.models import AuditLogEntry
from apps.accounts.permissions import require

from .models import Sale, SaleLine, SalesChannel
from .serializers import (
    SaleCreateSerializer,
    SaleCustomerSerializer,
    SaleDetailSerializer,
    SaleLineUpdateSerializer,
    SaleLineWriteSerializer,
    SaleListSerializer,
    SalesChannelSerializer,
    SaleUnitAddSerializer,
)
from .services.totals import SalesTotalsService
from .services.units import SaleUnitService

_VIEW = "sales.view"
_MANAGE = "orders.manage"


class SalesChannelViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = SalesChannel.objects.all()
    serializer_class = SalesChannelSerializer
    permission_classes = [require(_VIEW)]


class SaleViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Deliberately excludes ``UpdateModelMixin``/``DestroyModelMixin`` -- a
    sale is only ever changed via the ``lines``/``cancel`` actions below, and
    is never hard-deleted."""

    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in {"list", "retrieve"}:
            return [require(_VIEW)()]
        return [require(_MANAGE)()]

    def get_serializer_class(self):
        if self.action == "list":
            return SaleListSerializer
        if self.action == "create":
            return SaleCreateSerializer
        return SaleDetailSerializer

    def get_queryset(self):
        qs = Sale.objects.select_related("sales_channel").prefetch_related(
            "lines__variant__product"
        )
        params = self.request.query_params
        if channel := params.get("channel"):
            qs = qs.filter(sales_channel__code=channel)
        if status_ := params.get("status"):
            qs = qs.filter(status=status_)
        return qs

    def _detail_response(self, sale: Sale, status_code: int = 200) -> Response:
        sale = self.get_queryset().get(pk=sale.pk)
        return Response(
            SaleDetailSerializer(sale, context=self.get_serializer_context()).data,
            status=status_code,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sale = serializer.save()
        log_activity(actor=request.user, action=AuditLogEntry.Action.ORDER_CREATED, target=sale)
        return self._detail_response(sale, status_code=201)

    def _editable_sale(self, pk) -> Sale:
        sale = get_object_or_404(Sale, pk=pk)
        if not sale.is_editable:
            raise ValidationError(f"Sale is {sale.status} -- its lines can no longer be edited.")
        return sale

    @extend_schema(request=SaleLineWriteSerializer, responses=SaleDetailSerializer)
    @action(detail=True, methods=["post"], url_path="lines")
    def add_line(self, request, pk=None):
        sale = self._editable_sale(pk)
        serializer = SaleLineWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.create_line(sale)
        SalesTotalsService.recalculate(sale)
        return self._detail_response(sale)

    @extend_schema(request=SaleLineUpdateSerializer, responses=SaleDetailSerializer)
    @action(
        detail=True,
        methods=["patch", "delete"],
        url_path=r"lines/(?P<line_id>[^/.]+)",
    )
    def line_detail(self, request, pk=None, line_id=None):
        sale = self._editable_sale(pk)
        line = get_object_or_404(SaleLine, pk=line_id, sale=sale)
        if request.method == "DELETE":
            # A unit-backed line must release its reservations, not just
            # cascade-delete the join rows and leave units stuck RESERVED.
            unit_ids = list(line.units.values_list("serialized_unit_id", flat=True))
            if unit_ids:
                for unit_id in unit_ids:
                    SaleUnitService.remove(sale, unit_id, actor=request.user)
            else:
                line.delete()
        else:
            serializer = SaleLineUpdateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            serializer.apply(line)
        SalesTotalsService.recalculate(sale)
        return self._detail_response(sale)

    @extend_schema(request=SaleUnitAddSerializer, responses=SaleDetailSerializer)
    @action(detail=True, methods=["post"], url_path="units")
    def add_unit(self, request, pk=None):
        sale = self._editable_sale(pk)
        serializer = SaleUnitAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        SaleUnitService.add(
            sale,
            code=serializer.validated_data.get("code"),
            variant=serializer.validated_data.get("variant"),
            actor=request.user,
        )
        return self._detail_response(sale)

    @extend_schema(request=None, responses=SaleDetailSerializer)
    @action(
        detail=True,
        methods=["delete"],
        url_path=r"units/(?P<unit_id>[^/.]+)",
    )
    def remove_unit(self, request, pk=None, unit_id=None):
        sale = self._editable_sale(pk)
        SaleUnitService.remove(sale, unit_id, actor=request.user)
        return self._detail_response(sale)

    @extend_schema(request=SaleCustomerSerializer, responses=SaleDetailSerializer)
    @action(detail=True, methods=["post"], url_path="customer")
    def set_customer(self, request, pk=None):
        sale = self.get_object()
        serializer = SaleCustomerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sale.customer = serializer.validated_data.get("customer")
        sale.save(update_fields=["customer", "updated_at"])
        return self._detail_response(sale)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        sale = self.get_object()
        if sale.status in {Sale.Status.CANCELLED, Sale.Status.COMPLETED, Sale.Status.REFUNDED}:
            raise ValidationError(f"Sale is already {sale.status} -- it cannot be cancelled.")
        SaleUnitService.release_all(sale, actor=request.user)
        sale.status = Sale.Status.CANCELLED
        sale.save(update_fields=["status", "updated_at"])
        log_activity(actor=request.user, action=AuditLogEntry.Action.ORDER_CANCELLED, target=sale)
        return self._detail_response(sale)
