"""Inventory API viewsets.

Phase 3 ships ``Location`` **read-only** -- the Phase 3 serialized-unit work
needs to reference and display locations, but writing/transferring stock is the
Phase 4 ledger's job (ADR-007). Reads need ``inventory.view``.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter, SearchFilter

from apps.accounts.permissions import require

from .models import Location
from .serializers import LocationSerializer


class LocationViewSet(viewsets.ReadOnlyModelViewSet):
    """List / retrieve stock locations. Write access lands with the Phase 4 ledger."""

    serializer_class = LocationSerializer
    permission_classes = [require("inventory.view")]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "code"]
    ordering_fields = ["name", "created_at"]

    def get_queryset(self):
        qs = Location.objects.all()
        params = self.request.query_params
        if (kind := params.get("kind")) is not None:
            qs = qs.filter(kind=kind)
        if (is_active := params.get("is_active")) is not None:
            qs = qs.filter(is_active=is_active.lower() in {"1", "true", "yes"})
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
