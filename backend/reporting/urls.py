"""URLs du pilotage et des exports.

Chaque export existe en plusieurs formats ; le format est porté par
l'extension de la route et transmis à la vue (``export_format``), qui
n'a pas à le deviner.
"""

from django.urls import path

from . import views


def _export(vue, prefixe, nom, formats):
    return [
        path(
            f"exports/{prefixe}.{fmt}",
            vue.as_view(export_format=fmt),
            name=f"{nom}-{fmt}",
        )
        for fmt in formats
    ]


TABULAIRES = ("xlsx", "csv", "docx")

urlpatterns = [
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("dashboard/breakdown/", views.BreakdownView.as_view(), name="breakdown"),
    *_export(views.ExpensesExportView, "expenses", "export-expenses", TABULAIRES),
    *_export(
        views.ReconciliationExportView, "reconciliation", "export-reconciliation",
        TABULAIRES,
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
