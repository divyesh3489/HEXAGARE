from django.apps import AppConfig
from django.db.models.signals import post_migrate


class InventoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inventory"

    def ready(self) -> None:
        from .bootstrap import seed_locations

        # Seed the reference locations after this app's tables are migrated.
        post_migrate.connect(seed_locations, sender=self)
