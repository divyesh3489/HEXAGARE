"""Billing API (Phase 8).

- ``POST checkout/``           record payment against a DRAFT/RESERVED sale;
                                completes it (sells units, creates the
                                invoice) once payment covers the total,
                                otherwise leaves it RESERVED (on hold).
- ``invoices/``                list/retrieve generated invoices.
- ``invoices/{id}/pdf/``       download the rendered PDF (once READY).
- ``payments/``                list/retrieve recorded payments (``?sale=``).
"""

from __future__ import annotations

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import require
from apps.common.renderers import BinaryRenderer
from apps.sales.models import Sale

from .models import Invoice, Payment
from .serializers import (
    CheckoutResultSerializer,
    CheckoutSerializer,
    InvoiceDetailSerializer,
    InvoiceListSerializer,
    PaymentSerializer,
)
from .services.checkout import CompleteSaleService

_VIEW = "billing.view"
_MANAGE = "billing.manage"


class CheckoutView(APIView):
    """``POST /billing/checkout/`` -- the "Complete Sale" / "Collect payment"
    action, dispatching on the sale's current status. Always returns
    ``{"sale": ..., "invoice": ... | null}``.

    - ``DRAFT``/``RESERVED``: :meth:`CompleteSaleService.complete` -- becomes
      ``COMPLETED`` (units sold, invoice created) once payment covers the
      total, otherwise stays/becomes ``RESERVED`` (on hold, ``invoice: null``).
    - ``COMPLETED``: :meth:`CompleteSaleService.record_payment` -- settling
      more of a receivable (e.g. paying back a ``CREDIT`` balance); the
      existing invoice is returned with its ``balance_due`` now lower.
    """

    def get_permissions(self):
        return [require(_MANAGE)()]

    @extend_schema(request=CheckoutSerializer, responses=CheckoutResultSerializer)
    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sale_obj = serializer.validated_data["sale"]
        payments = serializer.validated_data.get("payments", [])

        if sale_obj.status == Sale.Status.COMPLETED:
            invoice = CompleteSaleService.record_payment(
                sale_obj, payments=payments, actor=request.user
            )
            sale = invoice.sale
        else:
            sale, invoice = CompleteSaleService.complete(
                sale_obj, payments=payments, actor=request.user
            )

        sale = (
            Sale.objects.select_related("sales_channel")
            .prefetch_related("lines__variant__product")
            .get(pk=sale.pk)
        )
        if invoice is not None:
            invoice = Invoice.objects.select_related("sale__sales_channel").get(pk=invoice.pk)
        data = CheckoutResultSerializer(
            {"sale": sale, "invoice": invoice}, context={"request": request}
        ).data
        return Response(data, status=200)


class InvoicePDFRenderer(BinaryRenderer):
    media_type = "application/pdf"
    format = "pdf"


class InvoiceViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [require(_VIEW)]

    def get_queryset(self):
        qs = Invoice.objects.select_related("sale__sales_channel").prefetch_related(
            "sale__lines__variant__product", "sale__payments", "deliveries"
        )
        params = self.request.query_params
        if sale := params.get("sale"):
            qs = qs.filter(sale_id=sale)
        if status_ := params.get("status"):
            qs = qs.filter(status=status_)
        return qs

    def get_serializer_class(self):
        return InvoiceListSerializer if self.action == "list" else InvoiceDetailSerializer

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], renderer_classes=[InvoicePDFRenderer])
    def pdf(self, request, pk=None):
        invoice = self.get_object()
        if invoice.status != Invoice.Status.READY or not invoice.pdf_file:
            raise serializers.ValidationError("This invoice's PDF is not ready yet.")
        with invoice.pdf_file.open("rb") as handle:
            data = handle.read()
        return Response(data, content_type="application/pdf")


class PaymentViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = PaymentSerializer
    permission_classes = [require(_VIEW)]

    def get_queryset(self):
        qs = Payment.objects.select_related("sale")
        params = self.request.query_params
        if sale := params.get("sale"):
            qs = qs.filter(sale_id=sale)
        return qs
