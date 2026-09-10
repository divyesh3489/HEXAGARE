"""Celery tasks for the accounts app."""

from __future__ import annotations

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task
def send_password_reset_email(email: str, uid: str, token: str) -> None:
    """Email a password-reset link. Enqueued by ``PasswordResetRequestView``;
    never sent inline on the request (per CLAUDE.md's Celery pattern)."""
    reset_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password?uid={uid}&token={token}"
    send_mail(
        subject="Reset your Hexagare password",
        message=(
            "We received a request to reset your Hexagare password.\n\n"
            f"Reset it here: {reset_url}\n\n"
            "If you did not request this, you can ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
