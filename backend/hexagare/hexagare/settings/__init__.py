"""Select the active settings module from the ``DJANGO_ENV`` env var.

    DJANGO_ENV=development  (default)
    DJANGO_ENV=staging
    DJANGO_ENV=production
    DJANGO_ENV=test
"""

import os

_ENV = os.environ.get("DJANGO_ENV", "development").strip().lower()

if _ENV == "production":
    from .production import *  # noqa: F401,F403
elif _ENV == "staging":
    from .staging import *  # noqa: F401,F403
elif _ENV == "test":
    from .test import *  # noqa: F401,F403
else:
    from .development import *  # noqa: F401,F403

DJANGO_ENV = _ENV
