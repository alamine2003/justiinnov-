"""URLs des comptes, de l'authentification, du référentiel et du back-office."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import referentiel, views

router = DefaultRouter()
router.register("countries", referentiel.CountryViewSet, basename="country")
router.register("managers", referentiel.ManagerViewSet, basename="manager")
router.register("teams", referentiel.TeamViewSet, basename="team")
router.register("cost-centers", referentiel.CostCenterViewSet, basename="cost-center")
router.register("projects", referentiel.ProjectViewSet, basename="project")
router.register("expense-titles", referentiel.ExpenseTitleViewSet, basename="expense-title")
router.register(
    "marketing-categories", referentiel.MarketingCategoryViewSet, basename="marketing-category"
)
router.register("history", referentiel.ChangeLogViewSet, basename="history")
router.register("users", views.UserViewSet, basename="user")

urlpatterns = [
    path(
        "token-auth/",
        views.ThrottledObtainAuthToken.as_view(),
        name="token-auth",
    ),
    path("me/", views.MeView.as_view(), name="me"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path(
        "permissions/",
        views.PermissionMatrixView.as_view(),
        name="permissions",
    ),
    path("me/password/", views.ChangePasswordView.as_view(), name="change-password"),
    # Les noms de ces deux routes sont exemptés du verrou de double
    # authentification (accounts.middleware) : sans eux, pas d'enrôlement.
    path("me/2fa/enrol/", views.TotpEnrolView.as_view(), name="totp-enrol"),
    path("me/2fa/confirm/", views.TotpConfirmView.as_view(), name="totp-confirm"),
    # Back-office : réservé au siège (cf. BackOfficePermission).
    path("configuration/", views.ConfigurationView.as_view(), name="configuration"),
    path(
        "workflow-configuration/",
        views.WorkflowConfigurationView.as_view(),
        name="workflow-configuration",
    ),
    path("", include(router.urls)),
]
