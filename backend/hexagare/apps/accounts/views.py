"""Auth, profile and password endpoints.

Token responses keep rest_framework_simplejwt's native ``{access, refresh}``
shape (plus ``user`` on login); single-resource responses return the object
directly. The list/error envelopes from ``apps.common`` apply to list and error
responses, which these are not.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import exceptions, mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.common.renderers import BinaryRenderer
from apps.common.utils import get_client_ip, get_user_agent

from .audit import AuditMixin, log_activity
from .models import AuditLogEntry, BackupJob, BusinessSettings, LoginHistory
from .permissions import require
from .rbac import OPERATIONAL_PERMISSIONS, ROLE_PERMISSIONS
from .serializers import (
    AuditLogEntrySerializer,
    BackupJobSerializer,
    BusinessSettingsSerializer,
    EmailTokenObtainPairSerializer,
    LogoutSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PermissionSerializer,
    ProfileUpdateSerializer,
    RolePermissionsSerializer,
    UserAdminCreateSerializer,
    UserAdminListSerializer,
    UserAdminUpdateSerializer,
    UserSerializer,
)
from .tasks import run_database_backup, send_password_reset_email

User = get_user_model()

_DetailResponse = inline_serializer("DetailResponse", {"detail": serializers.CharField()})
_SETTINGS_MANAGE = "settings.manage"
_USERS_MANAGE = "users.manage"
_AUDIT_VIEW = "audit.view"


def _record_login_event(request, event, *, user=None, email_attempted: str = "") -> None:
    LoginHistory.objects.create(
        user=user,
        email_attempted=email_attempted or "",
        event=event,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )


class LoginView(TokenObtainPairView):
    """Exchange email + password for an access/refresh pair. Records the attempt."""

    serializer_class = EmailTokenObtainPairSerializer
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        email = str(request.data.get("email", ""))
        try:
            serializer.is_valid(raise_exception=True)
        except exceptions.APIException:
            _record_login_event(
                request, LoginHistory.Event.LOGIN_FAILED, email_attempted=email
            )
            raise
        user = serializer.user
        _record_login_event(
            request,
            LoginHistory.Event.LOGIN_SUCCESS,
            user=user,
            email_attempted=user.email,
        )
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """Blacklist a refresh token so it (and its rotations) can't be reused."""

    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    @extend_schema(request=LogoutSerializer, responses={205: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _record_login_event(
            request,
            LoginHistory.Event.LOGOUT,
            user=request.user,
            email_attempted=request.user.email,
        )
        return Response(status=status.HTTP_205_RESET_CONTENT)


class ProfileView(RetrieveUpdateAPIView):
    """Read or update the authenticated user's own profile."""

    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return ProfileUpdateSerializer
        return UserSerializer

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        # Always echo the full user representation, not the writable subset.
        return Response(UserSerializer(self.get_object()).data)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PasswordChangeSerializer

    @extend_schema(request=PasswordChangeSerializer, responses={200: _DetailResponse})
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password updated."})


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    serializer_class = PasswordResetRequestSerializer

    @extend_schema(request=PasswordResetRequestSerializer, responses={200: _DetailResponse})
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        if result is not None:
            uid, token = result
            send_password_reset_email.delay(serializer.validated_data["email"], uid, token)
        return Response(
            {"detail": "If that email address has an account, a reset link has been sent."}
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    serializer_class = PasswordResetConfirmSerializer

    @extend_schema(request=PasswordResetConfirmSerializer, responses={200: _DetailResponse})
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Password has been reset. You can now sign in."})


# --------------------------------------------------------------------------- #
# Phase 17 -- Administration: settings, users, roles, audit log, backups
# --------------------------------------------------------------------------- #


class BusinessSettingsView(RetrieveUpdateAPIView):
    """The single editable ``BusinessSettings`` row. ``GET`` needs only to be
    authenticated (invoice numbering/serial-prefix previews elsewhere in the
    app read it indirectly); only ``settings.manage`` can change it."""

    serializer_class = BusinessSettingsSerializer

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [require(_SETTINGS_MANAGE)()]

    def get_object(self):
        return BusinessSettings.get_solo()

    # Always different on every save -- not real business info, so excluded
    # from the audit diff below (else every update logs a noise-only change).
    _DIFF_EXCLUDED = {"updated_at", "updated_by"}

    def perform_update(self, serializer):
        before = {k: v for k, v in BusinessSettingsSerializer(serializer.instance).data.items()}
        instance = serializer.save(updated_by=self.request.user)
        after = {k: v for k, v in BusinessSettingsSerializer(instance).data.items()}
        changes = {
            k: {"old": before.get(k), "new": v}
            for k, v in after.items()
            if k not in self._DIFF_EXCLUDED and before.get(k) != v
        }
        if changes:
            log_activity(
                actor=self.request.user,
                action=AuditLogEntry.Action.SETTINGS_UPDATED,
                target=instance,
                changes=changes,
                ip_address=get_client_ip(self.request),
            )


class UserViewSet(AuditMixin, viewsets.ModelViewSet):
    """Admin-only user management. No hard delete (section 53's "Delete
    restrictions/Soft delete") -- ``deactivate``/``reactivate`` toggle
    ``is_active`` instead of ``DestroyModelMixin``."""

    http_method_names = ["get", "post", "patch", "head", "options"]
    queryset = User.objects.prefetch_related("groups").order_by("email")
    permission_classes = [require(_USERS_MANAGE)]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["email", "first_name", "last_name"]
    ordering_fields = ["email", "date_joined", "last_login"]

    audit_created_action = AuditLogEntry.Action.USER_CREATED

    def get_queryset(self):
        qs = super().get_queryset()
        if (is_active := self.request.query_params.get("is_active")) is not None:
            qs = qs.filter(is_active=is_active.lower() in {"1", "true", "yes"})
        if role := self.request.query_params.get("role"):
            qs = qs.filter(groups__name=role)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return UserAdminCreateSerializer
        if self.action in {"update", "partial_update"}:
            return UserAdminUpdateSerializer
        return UserAdminListSerializer

    @staticmethod
    def _role_name(user) -> str | None:
        group = user.groups.first()
        return group.name if group else None

    def perform_update(self, serializer):
        user = serializer.instance
        before = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
            "role": self._role_name(user),
        }
        serializer.save()
        user.refresh_from_db()
        after = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
            "role": self._role_name(user),
        }
        changes = {k: {"old": before[k], "new": v} for k, v in after.items() if before[k] != v}
        if changes:
            log_activity(
                actor=self.request.user,
                action=AuditLogEntry.Action.USER_UPDATED,
                target=user,
                changes=changes,
                ip_address=get_client_ip(self.request),
            )

    def _detail(self, user) -> Response:
        return Response(UserAdminListSerializer(user).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = self.get_object()
        if not user.is_active:
            raise ValidationError("This user is already inactive.")
        user.is_active = False
        user.save(update_fields=["is_active"])
        log_activity(
            actor=request.user,
            action=AuditLogEntry.Action.USER_DEACTIVATED,
            target=user,
            ip_address=get_client_ip(request),
        )
        return self._detail(user)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        user = self.get_object()
        if user.is_active:
            raise ValidationError("This user is already active.")
        user.is_active = True
        user.save(update_fields=["is_active"])
        log_activity(
            actor=request.user,
            action=AuditLogEntry.Action.USER_REACTIVATED,
            target=user,
            ip_address=get_client_ip(request),
        )
        return self._detail(user)


class RolesView(APIView):
    """Read-only role -> permission matrix. Roles and their permission sets
    are code-defined in ``rbac.py`` (the single source of truth CLAUDE.md
    calls for) -- this only exposes them, it can't edit them."""

    permission_classes = [require(_USERS_MANAGE)]

    @extend_schema(
        responses=inline_serializer(
            "RolesResponse",
            {
                "roles": RolePermissionsSerializer(many=True),
                "permissions": PermissionSerializer(many=True),
            },
        )
    )
    def get(self, request):
        roles = [
            {"role": role, "permissions": sorted(codenames)}
            for role, codenames in ROLE_PERMISSIONS.items()
        ]
        permissions = [
            {"codename": codename, "name": name}
            for codename, name in sorted(OPERATIONAL_PERMISSIONS.items())
        ]
        return Response({"roles": roles, "permissions": permissions})


class AuditLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Read-only activity log. Filter by ``action``, ``actor``, ``object_type``
    (a model's lowercase name, e.g. ``product``), ``date_from``/``date_to``."""

    queryset = AuditLogEntry.objects.select_related("actor", "content_type").all()
    serializer_class = AuditLogEntrySerializer
    permission_classes = [require(_AUDIT_VIEW)]
    filter_backends = [OrderingFilter]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if action_ := params.get("action"):
            qs = qs.filter(action=action_)
        if actor := params.get("actor"):
            qs = qs.filter(actor_id=actor)
        if object_type := params.get("object_type"):
            qs = qs.filter(content_type__model=object_type.lower())
        if date_from := params.get("date_from"):
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to := params.get("date_to"):
            qs = qs.filter(created_at__date__lte=date_to)
        return qs


class BackupDownloadRenderer(BinaryRenderer):
    format = "file"


class BackupViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """``POST /backups/`` triggers a manual DB backup (async, via Celery);
    ``GET /backups/`` / ``GET /backups/{id}/`` is history; ``{id}/download/``
    streams the finished dump. Restore is not exposed -- see the Phase 17
    scope note in CLAUDE.md."""

    queryset = BackupJob.objects.select_related("triggered_by").all()
    serializer_class = BackupJobSerializer
    permission_classes = [require(_SETTINGS_MANAGE)]

    def create(self, request, *args, **kwargs):
        job = BackupJob.objects.create(triggered_by=request.user)
        log_activity(
            actor=request.user,
            action=AuditLogEntry.Action.BACKUP_TRIGGERED,
            target=job,
            ip_address=get_client_ip(request),
        )
        transaction.on_commit(lambda: run_database_backup.delay(job.pk))
        return Response(BackupJobSerializer(job).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], renderer_classes=[BackupDownloadRenderer])
    def download(self, request, pk=None):
        job = self.get_object()
        if job.status != BackupJob.Status.SUCCESS or not job.file:
            raise ValidationError("This backup is not ready yet.")
        with job.file.open("rb") as handle:
            data = handle.read()
        response = Response(data, content_type="application/octet-stream")
        filename = job.file.name.rsplit("/", 1)[-1]
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
