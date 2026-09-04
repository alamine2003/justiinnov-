"""URLs du pilotage et des exports."""

from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("dashboard/breakdown/", views.BreakdownView.as_view(), name="breakdown"),
    path(
        "exports/expenses.xlsx",
        views.ExpensesExportView.as_view(),
        name="export-expenses",
    ),
    path(
        "exports/reconciliation.xlsx",
        views.ReconciliationExportView.as_view(),
        name="export-reconciliation",
    ),
    path(
        "exports/report.pdf",
        views.CountryReportView.as_view(),
        name="export-report",
    ),
    path(
        "imports/expenses.xlsx",
        views.ExpensesImportView.as_view(),
        name="import-expenses",
    ),
]
