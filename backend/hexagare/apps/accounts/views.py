"""Auth, profile and password endpoints.

Token responses keep rest_framework_simplejwt's native ``{access, refresh}``
shape (plus ``user`` on login); single-resource responses return the object
directly. The list/error envelopes from ``apps.common`` apply to list and error
responses, which these are not.
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import exceptions, serializers, status
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.common.utils import get_client_ip, get_user_agent

from .models import LoginHistory
from .serializers import (
    EmailTokenObtainPairSerializer,
    LogoutSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileUpdateSerializer,
    UserSerializer,
)
from .tasks import send_password_reset_email

_DetailResponse = inline_serializer("DetailResponse", {"detail": serializers.CharField()})


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
