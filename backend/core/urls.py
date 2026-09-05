"""URLs de ``core`` : le point de santé, sans authentification.

Le référentiel, l'authentification et le back-office sont routés par
``accounts.urls`` (décision 40), aux mêmes chemins et sous les mêmes noms.
"""

from django.urls import path

from . import views

urlpatterns = [
    # Sans authentification : Docker et le déploiement s'en servent.
    path("health/", views.HealthView.as_view(), name="health"),
]
