from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import PurchaseOrderViewSet

app_name = "purchases"

# SimpleRouter (not DefaultRouter): PurchaseOrderViewSet is registered at
# "orders/", so DefaultRouter's API-root view would be pointless clutter
# (same reasoning as apps.sales.urls).
router = SimpleRouter()
router.register("orders", PurchaseOrderViewSet, basename="purchase-order")

urlpatterns = [
    path("", include(router.urls)),
]
