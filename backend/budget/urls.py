"""URLs des budgets."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("budgets", views.BudgetViewSet, basename="budget")
router.register(
    "reallocations", views.BudgetReallocationViewSet, basename="reallocation"
)
router.register("exchange-rates", views.ExchangeRateViewSet, basename="exchange-rate")

urlpatterns = [path("", include(router.urls))]
