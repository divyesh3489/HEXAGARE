"""
Shared Django settings for the Hexagare backend.

Environment-specific configuration lives in ``development.py`` / ``staging.py`` /
``production.py`` and is selected via the ``DJANGO_ENV`` env var (see
``settings/__init__.py``). Never put environment-specific config here.
"""

from datetime import timedelta
from pathlib import Path

import environ

# backend/hexagare  (the Django project root, holds manage.py)
BASE_DIR = Path(__file__).resolve().parents[2]
# repository root (holds docker-compose.yml and .env)
REPO_ROOT = BASE_DIR.parent.parent

env = environ.Env()
# Local .env for non-Docker development; under Docker Compose the values are
# injected into the environment via ``env_file`` so this is a harmless no-op.
environ.Env.read_env(REPO_ROOT / ".env")

# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #
SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-dev-only-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
ROOT_URLCONF = "hexagare.urls"
WSGI_APPLICATION = "hexagare.wsgi.application"
ASGI_APPLICATION = "hexagare.asgi.application"

# --------------------------------------------------------------------------- #
# Applications
# --------------------------------------------------------------------------- #
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "storages",
]

# Domain apps of the modular monolith. Add new functionality to the app it
# belongs to, not to a catch-all.
LOCAL_APPS = [
    "apps.common",
    "apps.accounts",
    "apps.products",
    "apps.inventory",
    "apps.sales",
    "apps.integrations",
    "apps.billing",
    "apps.customers",
    "apps.purchases",
    "apps.suppliers",
    "apps.expenses",
    "apps.reports",
    "apps.notifications",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://hexagare:hexagare@postgres:5432/hexagare",
    ),
}

# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# How long a password-reset link stays valid (seconds).
PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT", default=60 * 60 * 24)

# --------------------------------------------------------------------------- #
# i18n
# --------------------------------------------------------------------------- #
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------- #
# Static & media
# --------------------------------------------------------------------------- #
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Root-relative so serialized image URLs resolve against the caller's own origin
# (the Vite dev proxy forwards /media to the backend); S3 storage overrides this
# with absolute URLs anyway.
MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))

# Object storage. Django 5.1+ removed DEFAULT_FILE_STORAGE in favour of the
# STORAGES dict; the S3-vs-local switch is expressed there, keyed on USE_S3.
USE_S3 = env.bool("USE_S3", default=False)

if USE_S3:
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="")
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = True
    _default_storage = {"BACKEND": "storages.backends.s3.S3Storage"}
else:
    _default_storage = {"BACKEND": "django.core.files.storage.FileSystemStorage"}

STORAGES = {
    "default": _default_storage,
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# --------------------------------------------------------------------------- #
# DRF + API schema
# --------------------------------------------------------------------------- #
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # JWT is the API's primary auth; Session stays for the admin and the
        # browsable API during development.
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# --------------------------------------------------------------------------- #
# JWT (rest_framework_simplejwt)
# --------------------------------------------------------------------------- #
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=60)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=1)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Hexagare API",
    "DESCRIPTION": "Product / inventory / billing system API.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Schema and docs pages are browsable without auth; tighten if needed.
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    # Several models expose a ``status`` choice field; name each enum explicitly
    # so schema generation doesn't fall back to hash-suffixed names.
    "ENUM_NAME_OVERRIDES": {
        "ProductStatusEnum": "apps.products.models.Product.Status",
        "SerializedUnitStatusEnum": "apps.products.models.SerializedUnit.Status",
        "StockTransferStatusEnum": "apps.inventory.models.StockTransfer.Status",
        "InventoryTransactionKindEnum": "apps.inventory.models.InventoryTransaction.Kind",
    },
}

# --------------------------------------------------------------------------- #
# Celery
# --------------------------------------------------------------------------- #
CELERY_BROKER_URL = env("REDIS_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# --------------------------------------------------------------------------- #
# Hexagare domain config (SKU / serial-number formatting)
# --------------------------------------------------------------------------- #
HEXAGARE_SKU_PREFIX = env("HEXAGARE_SKU_PREFIX", default="HEX")
HEXAGARE_SERIAL_PREFIX = env("HEXAGARE_SERIAL_PREFIX", default="HX")
HEXAGARE_SERIAL_PADDING = env.int("HEXAGARE_SERIAL_PADDING", default=6)

# --------------------------------------------------------------------------- #
# Email / frontend links
# --------------------------------------------------------------------------- #
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@hexagare.local")
# Base URL of the SPA, used to build links in outbound email (password reset).
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default="http://localhost:5173")

# SMTP transport. The backend defaults to console here; development.py keeps
# that default and production.py switches to SMTP -- either can be overridden
# with DJANGO_EMAIL_BACKEND. The connection settings below are read whenever the
# SMTP backend is active, so set them in .env once and every environment uses
# them. (test.py forces the in-memory backend regardless.)
EMAIL_BACKEND = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=15)

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO")},
}
