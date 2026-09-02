"""Tableaux de bord temps réel (§5.6) et exports (§5.7)."""

from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from budget.aggregates import budget_figures, to_xof
from core.models import Country
from expenses.models import AuditLog
from notifications import triggers
from expenses.workflow import CONSUMING_STATUSES, ENGAGING_STATUSES, Status

from . import alerts as alert_rules
from .exports import (
    build_country_report_pdf,
    build_expenses_workbook,
    build_reconciliation_workbook,
)
from .scope import scoped_querysets

ZERO = Decimal("0.00")


def _as_int(value, field):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({field: "Valeur entière attendue."})


def _money(value):
    return str(value if value is not None else ZERO)


def _ratio(numerator, denominator):
    if not denominator:
        return None
    return str((Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001")))


class DashboardView(APIView):
    """Vue de pilotage : consolidation, répartition par pays et alertes."""

    def get(self, request):
        year = _as_int(request.query_params.get("year"), "year") or timezone.now().year
        country_id = _as_int(request.query_params.get("country"), "country")
        budgets, dossiers, expenses = scoped_querysets(request, year, country_id)

        rows, totals, consolidated = self._per_country(budgets)
        current_alerts = alert_rules.collect(budgets, dossiers, expenses)
        self._notify_budget_alerts(current_alerts)

        return Response(
            {
                "year": year,
                "totals": totals,
                "consolidated_xof": consolidated,
                "countries": rows,
                "workload": self._workload(dossiers, expenses),
                "alerts": current_alerts,
            }
        )

    def _notify_budget_alerts(self, current_alerts):
        """Transforme les alertes budgétaires en notifications persistantes.

        La clé d'unicité de chaque alerte garantit qu'un seuil franchi n'est
        signalé qu'une fois, quelle que soit la fréquence de consultation du
        tableau de bord.
        """
        budget_kinds = {"budget_threshold", "budget_overrun"}
        concerned = [a for a in current_alerts if a["kind"] in budget_kinds]
        if not concerned:
            return
        countries = {
            country.pk: country
            for country in Country.objects.filter(
                pk__in={a["country"] for a in concerned if a["country"]}
            )
        }
        for alert in concerned:
            country = countries.get(alert["country"])
            if country is not None:
                triggers.budget_alert(alert, country)

    def _per_country(self, budgets):
        """Agrège par pays ; seules les enveloppes de pays composent le total,
        les sous-enveloppes en étant un découpage."""
        per_country = defaultdict(
            lambda: {
                "allocated": ZERO, "sub_allocated": ZERO, "engaged": ZERO,
                "consumed": ZERO, "justified": ZERO,
            }
        )
        countries = {}

        for budget in budgets:
            entry = per_country[budget.country_id]
            countries[budget.country_id] = budget.country
            if budget.project_id is None:
                entry["allocated"] += budget.amount
            else:
                entry["sub_allocated"] += budget.amount
            figures = budget_figures(budget)
            entry["engaged"] += figures["engaged"]
            entry["consumed"] += figures["consumed"]
            entry["justified"] += figures["justified"]

        rows = []
        totals = defaultdict(lambda: ZERO)
        allocated_xof = ZERO
        remaining_xof_total = ZERO
        unconverted = set()

        for country_id, entry in per_country.items():
            country = countries[country_id]
            used = entry["consumed"] + entry["engaged"]
            remaining = entry["allocated"] - used
            for key, value in entry.items():
                totals[key] += value
            totals["remaining"] += remaining

            allocated_xof_row = to_xof(entry["allocated"], country.currency)
            remaining_xof = to_xof(remaining, country.currency)
            if remaining_xof is None or allocated_xof_row is None:
                unconverted.add(country.currency)
            else:
                allocated_xof += allocated_xof_row
                remaining_xof_total += remaining_xof

            rows.append(
                {
                    "country": country_id,
                    "country_name": country.name,
                    "country_ref": country.country_ref,
                    "currency": country.currency,
                    "allocated": _money(entry["allocated"]),
                    "sub_allocated": _money(entry["sub_allocated"]),
                    "engaged": _money(entry["engaged"]),
                    "consumed": _money(entry["consumed"]),
                    "justified": _money(entry["justified"]),
                    "gap": _money(entry["consumed"] - entry["justified"]),
                    "remaining": _money(remaining),
                    "execution_rate": _ratio(used, entry["allocated"]),
                    "justification_rate": _ratio(entry["justified"], entry["consumed"]),
                    "remaining_xof": (
                        str(remaining_xof) if remaining_xof is not None else None
                    ),
                }
            )

        rows.sort(key=lambda row: row["country_name"])
        used_total = totals["consumed"] + totals["engaged"]
        return (
            rows,
            {
                "allocated": _money(totals["allocated"]),
                "engaged": _money(totals["engaged"]),
                "consumed": _money(totals["consumed"]),
                "justified": _money(totals["justified"]),
                # Ce qui est sorti sans preuve à l'appui.
                "gap": _money(totals["consumed"] - totals["justified"]),
                "remaining": _money(totals["remaining"]),
                "execution_rate": _ratio(used_total, totals["allocated"]),
                "justification_rate": _ratio(totals["justified"], totals["consumed"]),
            },
            {
                "allocated": str(allocated_xof),
                "remaining": str(remaining_xof_total),
                # Une devise sans taux connu est exclue du total et signalée,
                # jamais absorbée silencieusement.
                "unconverted_currencies": sorted(unconverted),
            },
        )

    def _workload(self, dossiers, expenses):
        """Ce qui attend une action, pour orienter le contrôle."""
        by_status = dict(
            expenses.values_list("status").annotate(total=Count("id"))
        )
        return {
            "expenses_to_review": by_status.get(Status.SUBMITTED, 0)
            + by_status.get(Status.IN_REVIEW, 0),
            "expenses_draft": by_status.get(Status.DRAFT, 0),
            # Décaissements sans preuve : le chiffre que l'application existe
            # pour faire diminuer.
            "expenses_unjustified": by_status.get(Status.UNJUSTIFIED, 0),
            "dossiers_open": dossiers.exclude(status=Status.CLOSED).count(),
        }


class BreakdownView(APIView):
    """Répartition d'un pays par équipe, propriétaire, projet, catégorie et mois."""

    def get(self, request):
        year = _as_int(request.query_params.get("year"), "year") or timezone.now().year
        country_id = _as_int(request.query_params.get("country"), "country")
        _, _, expenses = scoped_querysets(request, year, country_id)

        # Brouillons et refus ne représentent aucune consommation réelle.
        counted = expenses.filter(
            status__in=list(ENGAGING_STATUSES) + list(CONSUMING_STATUSES)
        )
        return Response(
            {
                "year": year,
                "by_team": self._group(counted, "team__name", "Sans équipe"),
                "by_owner": self._group(counted, "owner__name", "Sans propriétaire"),
                "by_project": self._group(counted, "project__name", "Hors projet"),
                "by_category": self._group(
                    counted, "marketing_category__name", "Sans catégorie"
                ),
                "by_expense_title": self._group(
                    counted, "expense_title__label", "Sans intitulé"
                ),
                "by_month": self._by_month(counted),
            }
        )

    def _group(self, expenses, field, fallback):
        rows = (
            expenses.values(field)
            .annotate(
                amount=Sum("amount"),
                justified=Sum("justified_amount"),
                lines=Count("id"),
            )
            .order_by("-amount")
        )
        return [
            {
                "label": row[field] or fallback,
                "amount": _money(row["amount"]),
                "justified": _money(row["justified"]),
                "gap": _money((row["amount"] or ZERO) - (row["justified"] or ZERO)),
                "lines": row["lines"],
            }
            for row in rows
        ]

    def _by_month(self, expenses):
        rows = (
            expenses.annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(
                amount=Sum("amount"),
                justified=Sum("justified_amount"),
                lines=Count("id"),
            )
            .order_by("month")
        )
        return [
            {
                "label": row["month"].strftime("%Y-%m") if row["month"] else "—",
                "amount": _money(row["amount"]),
                "justified": _money(row["justified"]),
                "gap": _money((row["amount"] or ZERO) - (row["justified"] or ZERO)),
                "lines": row["lines"],
            }
            for row in rows
        ]


class ExportView(APIView):
    """Base des exports : périmètre appliqué, téléchargement tracé."""

    filename = "export"
    audit_label = "Export"

    def build(self, request, budgets, dossiers, expenses):  # pragma: no cover
        raise NotImplementedError

    def get(self, request):
        year = _as_int(request.query_params.get("year"), "year") or timezone.now().year
        country_id = _as_int(request.query_params.get("country"), "country")
        budgets, dossiers, expenses = scoped_querysets(request, year, country_id)

        content, content_type, filename = self.build(
            request, budgets, dossiers, expenses
        )
        self._audit(request, year, country_id, filename)

        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def _audit(self, request, year, country_id, filename):
        """Un export sort des données du système : il laisse une trace."""
        AuditLog.objects.create(
            user=request.user.username,
            action=AuditLog.Action.DOWNLOADED,
            object_type="Export",
            object_id=0,
            label=f"{self.audit_label} — {filename}",
            country_id=country_id,
            detail={"year": year, "country": country_id},
            ip_address=request.META.get("REMOTE_ADDR") or None,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:250],
        )


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ExpensesExportView(ExportView):
    """Export Excel au format du fichier historique."""

    audit_label = "Export des dépenses"

    def build(self, request, budgets, dossiers, expenses):
        workbook = build_expenses_workbook(dossiers)
        year = request.query_params.get("year") or timezone.now().year
        return workbook, XLSX, f"depenses-{year}.xlsx"


class ReconciliationExportView(ExportView):
    """Rapprochement dépenses / montants justifiés (§5.7)."""

    audit_label = "Rapport de rapprochement"

    def build(self, request, budgets, dossiers, expenses):
        workbook = build_reconciliation_workbook(budgets, dossiers)
        year = request.query_params.get("year") or timezone.now().year
        return workbook, XLSX, f"rapprochement-{year}.xlsx"


class CountryReportView(ExportView):
    """Rapport PDF par pays et période."""

    audit_label = "Rapport PDF"

    def build(self, request, budgets, dossiers, expenses):
        year = _as_int(request.query_params.get("year"), "year") or timezone.now().year
        pdf = build_country_report_pdf(budgets, dossiers, expenses, year)
        return pdf, "application/pdf", f"rapport-{year}.pdf"
