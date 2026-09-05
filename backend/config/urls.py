"""URL racine du projet."""

from django.contrib import admin
from django.urls import include, path

from .metriques import metriques
from .schema import SchemaUiView, SchemaView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Supervision (Prometheus → Grafana), sous jeton : voir config/metriques.py.
    path("metrics", metriques, name="metriques"),
    # Contrat d'API : le schéma pour le siège, son interface pour les
    # administrateurs en mode debug (config/schema.py).
    path("api/schema/", SchemaView.as_view(), name="schema"),
    path("api/schema/ui/", SchemaUiView.as_view(), name="schema-ui"),
    path("api/", include("core.urls")),
    path("api/", include("accounts.urls")),
    path("api/", include("budget.urls")),
    path("api/", include("expenses.urls")),
    path("api/", include("notifications.urls")),
    path("api/", include("reporting.urls")),
]