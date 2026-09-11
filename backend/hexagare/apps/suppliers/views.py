"""Suppliers API (Phase 12).

``suppliers/`` -- CRUD. Reads ``purchases.view`` (suppliers are viewed
alongside purchase orders, same nav grouping as rbac.py's "Purchases /
suppliers" section); writes ``suppliers.manage``. Deletion is blocked while
the supplier has any purchase-order history -- same guard style as
``inventory.Location`` / ``customers.Customer``.
"""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from apps.accounts.permissions import require

from .models import Supplier
from .serializers import SupplierDetailSerializer, SupplierListSerializer, SupplierWriteSerializer

_VIEW = "purchases.view"
_MANAGE = "suppliers.manage"
_READ_ACTIONS = {"list", "retrieve"}


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "company", "phone", "email", "gstin"]
    ordering_fields = ["name", "created_at"]

    def get_permissions(self):
        codename = _VIEW if self.action in _READ_ACTIONS else _MANAGE
        return [require(codename)()]

    def get_serializer_class(self):
        if self.action == "list":
            return SupplierListSerializer
        if self.action == "retrieve":
            return SupplierDetailSerializer
        return SupplierWriteSerializer

    def perform_destroy(self, instance):
        if instance.purchase_orders.exists():
            raise ValidationError(
                "This supplier has purchase-order history and cannot be deleted."
            )
        super().perform_destroy(instance)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        supplier = serializer.save()
        return self._detail_response(supplier, status_code=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        supplier = serializer.save()
        return self._detail_response(supplier)

    def _detail_response(self, supplier: Supplier, status_code: int = 200):
        return Response(
            SupplierDetailSerializer(supplier, context=self.get_serializer_context()).data,
            status=status_code,
        )
