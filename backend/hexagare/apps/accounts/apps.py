from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"

    def ready(self) -> None:
        from .rbac import ensure_role_groups

        # Materialize operational permissions + role groups after this app's
        # tables (and auth/contenttypes) are migrated. Idempotent.
        post_migrate.connect(ensure_role_groups, sender=self)
        post_migrate.connect(_ensure_business_settings, sender=self)


def _ensure_business_settings(**kwargs) -> None:
    """Guarantee the ``BusinessSettings`` singleton row (pk=1) exists, same
    bootstrap-on-migrate pattern as ``Location``/``SalesChannel``."""
    from .models import BusinessSettings

    BusinessSettings.get_solo()
