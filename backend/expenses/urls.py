"""URLs des dépenses et justificatifs."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("beneficiaries", views.BeneficiaryViewSet, basename="beneficiary")
router.register("dossiers", views.DossierViewSet, basename="dossier")
router.register("expenses", views.ExpenseViewSet, basename="expense")
router.register("proofs", views.ProofViewSet, basename="proof")
router.register("audit", views.AuditLogViewSet, basename="audit")

urlpatterns = [path("", include(router.urls))]
