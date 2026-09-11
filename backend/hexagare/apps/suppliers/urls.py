from rest_framework.routers import SimpleRouter

from .views import SupplierViewSet

app_name = "suppliers"

router = SimpleRouter()
router.register("", SupplierViewSet, basename="supplier")

urlpatterns = router.urls
