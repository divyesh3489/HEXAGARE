from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import LocationViewSet

app_name = "inventory"

router = SimpleRouter()
router.register("locations", LocationViewSet, basename="location")

urlpatterns = [
    path("", include(router.urls)),
]
