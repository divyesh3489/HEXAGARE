"""Root URLconf for the integrations app -- mounts the Amazon sub-app at
``/api/v1/integrations/amazon/``. Future channel integrations get their own
``path()`` entry here alongside ``amazon/``.
"""

from django.urls import include, path

app_name = "integrations"

urlpatterns = [
    path("amazon/", include("apps.integrations.amazon.urls")),
]
