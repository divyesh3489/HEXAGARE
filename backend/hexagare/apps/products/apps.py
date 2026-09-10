from django.apps import AppConfig
from django.db.models.signals import post_migrate


class ProductsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.products"

    def ready(self) -> None:
        from .bootstrap import seed_label_sizes

        # Seed default label sizes after this app's tables are migrated.
        post_migrate.connect(seed_label_sizes, sender=self)
