"""Staging settings - production-like, with a few relaxations."""

from .production import *  # noqa: F401,F403
from .production import env

# Staging often runs without the full HSTS commitment.
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_PRELOAD = False
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
