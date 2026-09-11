from django.apps import AppConfig
from django.db.models.signals import post_migrate


class SalesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sales"

    def ready(self) -> None:
        from .bootstrap import seed_sales_channels

        # Seed the reference sales channels after this app's tables are migrated.
        post_migrate.connect(seed_sales_channels, sender=self)
