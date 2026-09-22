"""URL racine du projet."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from .metriques import metriques
from .schema import SchemaUiView, SchemaView

# Ce qui échappe à DRF — une URL inconnue, un hôte refusé, une exception
# levée hors d'une vue — rendait une page HTML à un client qui attend du
# JSON. Ces quatre gestionnaires la rendent en JSON sous ``/api/`` et pour
# qui la demande ; l'admin Django, monté en développement, garde ses pages.
handler400 = "core.exceptions.erreur_400"
handler403 = "core.exceptions.erreur_403"
handler404 = "core.exceptions.erreur_404"
handler500 = "core.exceptions.erreur_500"

urlpatterns = [
    *([path("admin/", admin.site.urls)] if settings.ADMIN_ENABLED else []),
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