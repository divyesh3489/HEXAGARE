from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import SalesChannelViewSet, SaleViewSet

app_name = "sales"

# SimpleRouter (not DefaultRouter): SaleViewSet is registered at this app's
# root prefix, so DefaultRouter's API-root view would collide with the sale
# list route (same reasoning as apps.products.urls).
router = SimpleRouter()
router.register("channels", SalesChannelViewSet, basename="sales-channel")
router.register("", SaleViewSet, basename="sale")

urlpatterns = [
    path("", include(router.urls)),
]
