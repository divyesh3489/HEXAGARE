from rest_framework.routers import SimpleRouter

from .views import ReportExportViewSet, ReportsViewSet

app_name = "reports"

router = SimpleRouter()
router.register("exports", ReportExportViewSet, basename="report-export")
router.register("", ReportsViewSet, basename="report")

urlpatterns = router.urls
