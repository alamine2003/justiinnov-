"""URLs des comptes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("users", views.UserViewSet, basename="user")

urlpatterns = [
    path("me/", views.MeView.as_view(), name="me"),
    path(
        "configuration/",
        views.ConfigurationView.as_view(),
        name="configuration",
    ),
    path(
        "permissions/",
        views.PermissionMatrixView.as_view(),
        name="permissions",
    ),
    path("me/password/", views.ChangePasswordView.as_view(), name="change-password"),
    path("", include(router.urls)),
]
