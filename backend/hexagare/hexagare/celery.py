"""Celery application for Hexagare.

Task modules live in each domain app as ``apps/<app>/tasks.py`` and are picked
up by ``autodiscover_tasks()``.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hexagare.settings")

app = Celery("hexagare")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
