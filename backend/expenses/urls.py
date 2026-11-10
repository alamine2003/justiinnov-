"""URLs des dépenses et justificatifs."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import projets, views

router = DefaultRouter()
# Les projets vivent ici depuis la décision 125 : ils ouvrent des dossiers.
router.register("projects", projets.ProjectViewSet, basename="project")
router.register("beneficiaries", views.BeneficiaryViewSet, basename="beneficiary")
router.register("dossiers", views.DossierViewSet, basename="dossier")
router.register("expenses", views.ExpenseViewSet, basename="expense")
router.register("proofs", views.ProofViewSet, basename="proof")
router.register("rectifications", views.RectificationViewSet, basename="rectification")
router.register("audit", views.AuditLogViewSet, basename="audit")
router.register("corbeille", views.CorbeilleViewSet, basename="corbeille")

urlpatterns = [path("", include(router.urls))]
