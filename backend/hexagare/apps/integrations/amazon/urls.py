from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    AmazonFeeConfigViewSet,
    AmazonImportBatchViewSet,
    AmazonOrderSettlementViewSet,
    AmazonSkuMappingViewSet,
)

router = SimpleRouter()
router.register("imports", AmazonImportBatchViewSet, basename="amazon-import")
router.register("sku-mappings", AmazonSkuMappingViewSet, basename="amazon-sku-mapping")
router.register("fee-config", AmazonFeeConfigViewSet, basename="amazon-fee-config")
router.register("settlements", AmazonOrderSettlementViewSet, basename="amazon-settlement")

urlpatterns = [
    path("", include(router.urls)),
]
