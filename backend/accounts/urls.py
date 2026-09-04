"""URLs des comptes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("users", views.UserViewSet, basename="user")

urlpatterns = [
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
    path("", include(router.urls)),
]
