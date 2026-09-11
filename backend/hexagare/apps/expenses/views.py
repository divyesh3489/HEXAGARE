"""Expenses + finance API (Phase 13).

- ``expenses/``                       -- CRUD (``expenses.manage``).
- ``expenses/finance/summary/``       -- gross/net profit for a date range,
  optionally one channel (``finance.view``).
- ``expenses/finance/by-channel/``    -- the same summary per active
  ``SalesChannel`` (``finance.view``).
- ``expenses/finance/units/{unit_id}/profit/`` -- section 37 per-serial
  profit breakdown (``finance.view``).
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.accounts.permissions import require
from apps.products.models import SerializedUnit
from apps.sales.models import SalesChannel

from .models import Expense
from .serializers import (
    DateRangeQuerySerializer,
    ExpenseSerializer,
    FinanceSummarySerializer,
    UnitProfitSerializer,
)
from .services import FinanceService

_MANAGE = "expenses.manage"
_FINANCE_VIEW = "finance.view"


class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.select_related("sales_channel", "created_by").all()
    serializer_class = ExpenseSerializer
    permission_classes = [require(_MANAGE)]
    filter_backends = [OrderingFilter]
    ordering_fields = ["expense_date", "amount", "created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if category := params.get("category"):
            qs = qs.filter(category=category)
        if channel := params.get("channel"):
            qs = qs.filter(sales_channel__code=channel)
        if date_from := params.get("date_from"):
            qs = qs.filter(expense_date__gte=date_from)
        if date_to := params.get("date_to"):
            qs = qs.filter(expense_date__lte=date_to)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


def _resolve_channel(code: str | None) -> SalesChannel | None:
    if not code:
        return None
    try:
        return SalesChannel.objects.get(code=code)
    except SalesChannel.DoesNotExist as exc:
        raise ValidationError({"channel": f"Unknown sales channel {code!r}."}) from exc


class FinanceViewSet(GenericViewSet):
    """No ``queryset`` -- every action computes its response from
    ``FinanceService`` rather than a model queryset; ``serializer_class``
    below is only the schema-generation default."""

    permission_classes = [require(_FINANCE_VIEW)]
    serializer_class = FinanceSummarySerializer

    def _date_range(self, request):
        query = DateRangeQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        channel = _resolve_channel(data.get("channel"))
        return data["date_from"], data["date_to"], channel

    @extend_schema(responses=FinanceSummarySerializer)
    @action(detail=False, methods=["get"])
    def summary(self, request):
        date_from, date_to, channel = self._date_range(request)
        data = FinanceService.summary(date_from, date_to, channel)
        return Response(FinanceSummarySerializer(data).data)

    @extend_schema(responses=FinanceSummarySerializer(many=True))
    @action(detail=False, methods=["get"], url_path="by-channel")
    def by_channel(self, request):
        date_from, date_to, _channel = self._date_range(request)
        data = FinanceService.by_channel(date_from, date_to)
        return Response(FinanceSummarySerializer(data, many=True).data)

    @extend_schema(responses=UnitProfitSerializer)
    @action(
        detail=False,
        methods=["get"],
        url_path=r"units/(?P<unit_id>[^/.]+)/profit",
    )
    def unit_profit(self, request, unit_id=None):
        unit = get_object_or_404(SerializedUnit, pk=unit_id)
        data = FinanceService.unit_profit(unit)
        return Response(UnitProfitSerializer(data).data)
