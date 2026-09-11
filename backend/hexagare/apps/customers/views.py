"""Customers API (Phase 11).

``customers/`` -- CRUD. Reads ``customers.view``; writes ``customers.manage``.
Deletion is blocked while the customer has any sales history -- same guard
style as ``inventory.Location``.
"""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from apps.accounts.permissions import require

from .models import Customer
from .serializers import CustomerDetailSerializer, CustomerListSerializer, CustomerWriteSerializer

_VIEW = "customers.view"
_MANAGE = "customers.manage"
_READ_ACTIONS = {"list", "retrieve"}


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "phone", "email", "gstin"]
    ordering_fields = ["name", "created_at"]

    def get_permissions(self):
        codename = _VIEW if self.action in _READ_ACTIONS else _MANAGE
        return [require(codename)()]

    def get_serializer_class(self):
        if self.action == "list":
            return CustomerListSerializer
        if self.action == "retrieve":
            return CustomerDetailSerializer
        return CustomerWriteSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if (type_ := self.request.query_params.get("type")) is not None:
            qs = qs.filter(type=type_)
        return qs

    def perform_destroy(self, instance):
        if instance.sales.exists():
            raise ValidationError(
                "This customer has sales history and cannot be deleted."
            )
        super().perform_destroy(instance)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()
        return self._detail_response(customer, status_code=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        customer = serializer.save()
        return self._detail_response(customer)

    def _detail_response(self, customer: Customer, status_code: int = 200):
        return Response(
            CustomerDetailSerializer(customer, context=self.get_serializer_context()).data,
            status=status_code,
        )
