"""Celery tasks for the accounts app."""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from urllib.parse import urlparse

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


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


def _pg_dump_env_and_args() -> tuple[list[str], dict[str, str]]:
    """Build the ``pg_dump`` argv + a ``PGPASSWORD``-carrying env from
    ``settings.DATABASES["default"]`` (populated by ``django-environ``'s
    ``env.db()`` from ``DATABASE_URL``)."""
    db = settings.DATABASES["default"]
    args = ["pg_dump", "-Fc", "--no-owner", "--no-privileges"]
    host = db.get("HOST")
    port = db.get("PORT")
    user = db.get("USER")
    if host:
        args += ["-h", str(host)]
    if port:
        args += ["-p", str(port)]
    if user:
        args += ["-U", str(user)]
    args.append(str(db["NAME"]))

    env = dict(os.environ)
    if password := db.get("PASSWORD"):
        env["PGPASSWORD"] = str(password)
    return args, env


@shared_task
def run_database_backup(job_id: int) -> str:
    """Manual DB backup (HEXAGARE_FEATURES.md section 54): ``pg_dump -Fc``
    (a compact, ``pg_restore``-compatible dump), uploaded to the same storage
    backend as every other generated file. Recoverable-by-design, same
    PENDING/RUNNING -> SUCCESS/FAILED shape as ``apps.reports.tasks.
    generate_report_export`` -- a failure just records ``error_message``.

    Restore and scheduled/automatic backups are out of scope (Phase 17
    narrowed this to "manual backup command + history" -- see CLAUDE.md).
    """
    from .models import BackupJob

    try:
        job = BackupJob.objects.get(pk=job_id)
    except BackupJob.DoesNotExist:
        return "missing"

    job.status = BackupJob.Status.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])

    args, env = _pg_dump_env_and_args()
    db_name = urlparse(os.environ.get("DATABASE_URL", "")).path.lstrip("/") or "hexagare"

    try:
        with tempfile.TemporaryFile() as dump_file:
            result = subprocess.run(  # noqa: S603 - fixed argv, no shell, no user input
                args, stdout=dump_file, stderr=subprocess.PIPE, env=env, timeout=1800
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode(errors="replace")[:2000])
            dump_file.seek(0)
            data = dump_file.read()
    except Exception as exc:  # noqa: BLE001 - record and stop; recoverable
        logger.exception("Database backup failed for job %s", job_id)
        job.status = BackupJob.Status.FAILED
        job.error_message = str(exc)[:2000]
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error_message", "finished_at"])
        return "failed"

    filename = f"hexagare-{db_name}-{timezone.now():%Y%m%d-%H%M%S}.dump"
    job.file.save(filename, ContentFile(data), save=False)
    job.file_size = len(data)
    job.status = BackupJob.Status.SUCCESS
    job.error_message = ""
    job.finished_at = timezone.now()
    job.save(update_fields=["file", "file_size", "status", "error_message", "finished_at"])
    return "success"
