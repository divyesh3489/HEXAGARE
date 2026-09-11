"""Triggers registration of the Amazon admin classes -- Django's
``admin.autodiscover()`` imports ``<app>.admin`` for each installed app. See
``apps/integrations/amazon/admin.py``.
"""

from .amazon import admin as _amazon_admin  # noqa: F401
