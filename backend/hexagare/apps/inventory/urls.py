from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    InventoryAdjustmentView,
    InventoryAlertsView,
    InventoryBalanceViewSet,
    InventoryOverviewView,
    InventoryTransactionViewSet,
    LocationViewSet,
    StockLevelPolicyViewSet,
    StockTransferViewSet,
)

app_name = "inventory"

router = SimpleRouter()
router.register("locations", LocationViewSet, basename="location")
router.register("balances", InventoryBalanceViewSet, basename="balance")
router.register("transactions", InventoryTransactionViewSet, basename="transaction")
router.register("policies", StockLevelPolicyViewSet, basename="policy")
router.register("transfers", StockTransferViewSet, basename="transfer")

urlpatterns = [
    path("overview/", InventoryOverviewView.as_view(), name="overview"),
    path("alerts/", InventoryAlertsView.as_view(), name="alerts"),
    path("adjustments/", InventoryAdjustmentView.as_view(), name="adjustments"),
    path("", include(router.urls)),
]
