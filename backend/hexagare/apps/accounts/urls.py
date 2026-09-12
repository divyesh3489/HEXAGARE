from django.urls import path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AuditLogViewSet,
    BackupViewSet,
    BusinessSettingsView,
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ProfileView,
    RolesView,
    UserViewSet,
)

app_name = "accounts"

router = SimpleRouter()
router.register("users", UserViewSet, basename="user")
router.register("audit-log", AuditLogViewSet, basename="audit-log")
router.register("backups", BackupViewSet, basename="backup")

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("password/change/", PasswordChangeView.as_view(), name="password-change"),
    path("password/reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path(
        "password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("settings/", BusinessSettingsView.as_view(), name="settings"),
    path("roles/", RolesView.as_view(), name="roles"),
] + router.urls
