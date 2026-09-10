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
