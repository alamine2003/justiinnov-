"""URLs de l'API."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("countries", views.CountryViewSet, basename="country")
router.register("managers", views.ManagerViewSet, basename="manager")
router.register("teams", views.TeamViewSet, basename="team")
router.register("cost-centers", views.CostCenterViewSet, basename="cost-center")
router.register("projects", views.ProjectViewSet, basename="project")
router.register("expense-titles", views.ExpenseTitleViewSet, basename="expense-title")
router.register("marketing-categories", views.MarketingCategoryViewSet, basename="marketing-category")
router.register("history", views.ChangeLogViewSet, basename="history")

urlpatterns = [
    path(
        "token-auth/",
        views.ThrottledObtainAuthToken.as_view(),
        name="token-auth",
    ),
    path("", include(router.urls)),
]