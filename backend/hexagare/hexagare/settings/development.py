"""Local development settings."""

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])

# Prints emails to the container logs by default; set DJANGO_EMAIL_BACKEND to
# django.core.mail.backends.smtp.EmailBackend (+ EMAIL_HOST/USER/PASSWORD in
# .env) to send real mail from development.
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
