from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    CategoryViewSet,
    LabelSizeViewSet,
    ProductAttributeViewSet,
    ProductImageViewSet,
    ProductVariantViewSet,
    ProductViewSet,
    SkuAvailabilityView,
    SkuSuggestionView,
)

app_name = "products"

# SimpleRouter (not DefaultRouter): ``ProductViewSet`` is registered at this
# app's root prefix, so DefaultRouter's API-root view would collide with the
# product list route.
router = SimpleRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("attributes", ProductAttributeViewSet, basename="attribute")
router.register("variants", ProductVariantViewSet, basename="variant")
router.register("images", ProductImageViewSet, basename="image")
router.register("label-sizes", LabelSizeViewSet, basename="label-size")
router.register("", ProductViewSet, basename="product")

urlpatterns = [
    path("sku/suggest/", SkuSuggestionView.as_view(), name="sku-suggest"),
    path("sku/check/", SkuAvailabilityView.as_view(), name="sku-check"),
    path("", include(router.urls)),
]
