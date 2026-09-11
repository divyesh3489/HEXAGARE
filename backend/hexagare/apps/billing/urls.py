from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import CheckoutView, InvoiceViewSet, PaymentViewSet

app_name = "billing"

router = SimpleRouter()
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("payments", PaymentViewSet, basename="payment")

urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("", include(router.urls)),
]
