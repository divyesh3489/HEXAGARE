"""Re-exports the Amazon Celery tasks so ``celery.py``'s
``autodiscover_tasks()`` (which looks for ``<app>.tasks``) finds them. See
``apps/integrations/amazon/tasks.py``.
"""

from .amazon.tasks import import_amazon_orders  # noqa: F401
