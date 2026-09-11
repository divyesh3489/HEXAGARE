from rest_framework.routers import SimpleRouter

from .views import ExpenseViewSet, FinanceViewSet

app_name = "expenses"

router = SimpleRouter()
router.register("finance", FinanceViewSet, basename="finance")
router.register("", ExpenseViewSet, basename="expense")

urlpatterns = router.urls
