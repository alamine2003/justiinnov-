"""URL racine du projet."""

from django.contrib import admin
from django.urls import include, path

from .metriques import metriques

urlpatterns = [
    path("admin/", admin.site.urls),
    # Supervision (Prometheus → Grafana), sous jeton : voir config/metriques.py.
    path("metrics", metriques, name="metriques"),
    path("api/", include("core.urls")),
    path("api/", include("accounts.urls")),
    path("api/", include("budget.urls")),
    path("api/", include("expenses.urls")),
    path("api/", include("notifications.urls")),
    path("api/", include("reporting.urls")),
]