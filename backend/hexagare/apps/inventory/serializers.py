"""Serializers for the inventory API.

Phase 3 exposes ``Location`` read-only (see ADR-007); the ledger serializers
arrive in Phase 4.
"""

from __future__ import annotations

from rest_framework import serializers

from .models import Location


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "name", "code", "kind", "is_active"]
