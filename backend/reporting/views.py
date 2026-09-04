"""Tableaux de bord temps réel (§5.6) et exports (§5.7)."""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import FormParser, MultiPartParser

from budget.aggregates import consolidation_par_pays, current_rates, to_xof
from core.requetes import client_ip
from expenses.models import AuditLog
from expenses.workflow import CONSUMING_STATUSES, ENGAGING_STATUSES, Status

from . import alerts as alert_rules
from .exports import (
    build_country_report_pdf,
    build_expenses_workbook,
    build_reconciliation_workbook,
)
from .scope import scoped_querysets
from accounts.permissions import EXPENSE_WRITE_ROLES, RolePermission, get_access
from .imports import audit_import, importer_depenses

ZERO = Decimal("0.00")

#: Nombre d'alertes transmises au tableau de bord, les plus graves d'abord.
MAX_ALERTS = 50


def _as_int(value, field):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({field: "Valeur entière attendue."})


def _pays_unique(request):
    """Le seul pays du périmètre, ou ``None`` s'il y en a zéro ou plusieurs."""
    access = get_access(request.user)
    if access is None or access.has_global_scope:
        return None
    ids = list(access.country_ids)
    return ids[0] if len(ids) == 1 else None


def _money(value):
    return str(value if value is not None else ZERO)


def _ratio(numerator, denominator):
    if not denominator:
        return None
    return str((Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001")))


def _as_str(value):
    return str(value) if value is not None else None


class DashboardView(APIView):
    """Vue de pilotage : consolidation, répartition par pays et alertes."""

    def get(self, request):
        year = _as_int(request.query_params.get("year"), "year") or timezone.now().year
        country_id = _as_int(request.query_params.get("country"), "country")
        budgets, dossiers, expenses = scoped_querysets(request, year, country_id)

        rows, _, consolidated = self._per_country(budgets)
        current_alerts = alert_rules.collect(budgets, dossiers, expenses)

        return Response(
            {
                "year": year,
                # Les totaux en devise n'existent que par pays : au niveau
                # global, seul le FCFA consolidé a un sens.
                "totals": self._totaux_consolides(rows),
                "consolidated_xof": consolidated,
                "countries": rows,
                "workload": self._workload(dossiers, expenses),
                # Les alertes sont calculées à la lecture, mais **pas
                # notifiées** ici : une requête GET ne doit rien écrire, et
                # faire dépendre l'alerte de l'ouverture d'une page reviendrait
                # à n'avertir personne les jours où nul ne regarde. C'est la
                # commande `notify_alerts` qui s'en charge.
                #
                # Seules les plus graves sont transmises : en renvoyer cent
                # trente alourdirait la réponse sans que l'écran les montre.
                "alerts": current_alerts[:MAX_ALERTS],
                "alerts_total": len(current_alerts),
            }
        )

    #: Chiffres d'une ligne de pays qui se consolident en FCFA.
    MONTANTS = ("allocated", "engaged", "consumed", "justified", "remaining")

    def _totaux_consolides(self, rows):
        """Totaux globaux, en FCFA uniquement.

        Additionner « allocated » du Togo (XOF) et du Ghana (GHS) donnait un
        chiffre sans unité, présenté comme un total. Chaque montant est
        converti au taux courant ; un pays dont la devise n'a pas de taux est
        écarté et nommé, jamais absorbé.
        """
        rates = current_rates()
        totaux = {key: ZERO for key in self.MONTANTS}
        non_converties = set()
        for row in rows:
            montants = {
                key: to_xof(Decimal(row[key]), row["currency"], rates=rates)
                for key in self.MONTANTS
            }
            if any(value is None for value in montants.values()):
                non_converties.add(row["currency"])
                continue
            for key, value in montants.items():
                totaux[key] += value

        used = totaux["consumed"] + totaux["engaged"]
        return {
            "currency": "XOF",
            **{key: _money(value) for key, value in totaux.items()},
            # Ce qui est sorti sans preuve à l'appui.
            "gap": _money(totaux["consumed"] - totaux["justified"]),
            "execution_rate": _ratio(used, totaux["allocated"]),
            "justification_rate": _ratio(totaux["justified"], totaux["consumed"]),
            "unconverted_currencies": sorted(non_converties),
        }

    def _per_country(self, budgets):
        """Agrège par pays via :func:`consolidation_par_pays`, seul point de
        calcul partagé avec ``/api/budgets/summary/``."""
        rows, consolidated = consolidation_par_pays(budgets, rates=current_rates())

        # Totaux en devises locales additionnées : conservés tels quels pour
        # ne pas changer le contrat de la vue ici ; le sens n'en est assuré
        # que lorsque tous les pays partagent la même devise.
        totals = defaultdict(lambda: ZERO)
        for row in rows:
            for key in ("allocated", "engaged", "consumed", "justified", "remaining"):
                totals[key] += row[key]
        used_total = totals["consumed"] + totals["engaged"]

        return (
            [
                {
                    "country": row["country"],
                    "country_name": row["country_name"],
                    "country_ref": row["country_ref"],
                    "currency": row["currency"],
                    "allocated": _money(row["allocated"]),
                    "sub_allocated": _money(row["sub_allocated"]),
                    "engaged": _money(row["engaged"]),
                    "consumed": _money(row["consumed"]),
                    "justified": _money(row["justified"]),
                    "gap": _money(row["gap"]),
                    "remaining": _money(row["remaining"]),
                    "execution_rate": _as_str(row["execution_rate"]),
                    "justification_rate": _as_str(row["justification_rate"]),
                    "remaining_xof": _as_str(row["remaining_xof"]),
                }
                for row in rows
            ],
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
                "allocated": str(consolidated["allocated"]),
                "remaining": str(consolidated["remaining"]),
                # Une devise sans taux connu est exclue du total et signalée,
                # jamais absorbée silencieusement.
                "unconverted_currencies": consolidated["unconverted_currencies"],
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
        if not country_id:
            # Sans pays, deux équipes homonymes de pays différents — et de
            # devises différentes — fusionneraient dans une même ligne. Un
            # compte restreint à un seul pays n'a rien à choisir : il obtient
            # sa répartition sans avoir à nommer ce pays.
            country_id = _pays_unique(request)
        if not country_id:
            raise ValidationError({"country": "Le pays est obligatoire."})
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

    def build(self, budgets, dossiers, expenses, year):  # pragma: no cover
        raise NotImplementedError

    def get(self, request):
        year = _as_int(request.query_params.get("year"), "year") or timezone.now().year
        country_id = _as_int(request.query_params.get("country"), "country")
        # Le pays est vérifié contre le périmètre par ``scoped_querysets`` :
        # un identifiant inconnu ou étranger répond 404 avant tout calcul.
        budgets, dossiers, expenses = scoped_querysets(request, year, country_id)

        # L'année validée sert aussi au nom du fichier : reprise brute de la
        # requête, elle y injectait ce que le client voulait.
        content, content_type, filename = self.build(budgets, dossiers, expenses, year)
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
            ip_address=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:250],
        )


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ExpensesExportView(ExportView):
    """Export Excel au format du fichier historique."""

    audit_label = "Export des dépenses"

    def build(self, budgets, dossiers, expenses, year):
        return build_expenses_workbook(dossiers), XLSX, f"depenses-{year}.xlsx"


class ReconciliationExportView(ExportView):
    """Rapprochement dépenses / montants justifiés (§5.7)."""

    audit_label = "Rapport de rapprochement"

    def build(self, budgets, dossiers, expenses, year):
        workbook = build_reconciliation_workbook(budgets, dossiers)
        return workbook, XLSX, f"rapprochement-{year}.xlsx"


class CountryReportView(ExportView):
    """Rapport PDF par pays et période."""

    audit_label = "Rapport PDF"

    def build(self, budgets, dossiers, expenses, year):
        pdf = build_country_report_pdf(budgets, dossiers, expenses, year)
        return pdf, "application/pdf", f"rapport-{year}.pdf"


class ExpensesImportView(APIView):
    """Importe le format exact de l'export des dépenses.

    Réservé aux rôles de saisie : importer, c'est déclarer. Un contrôleur ou
    la direction des opérations lisent et constatent, ils ne déclarent pas.
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [RolePermission]
    write_roles = EXPENSE_WRITE_ROLES

    def post(self, request):
        self.check_permissions(request)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationError({"file": "Le champ file est obligatoire."})
        dry_run = str(request.query_params.get("dry_run", "false")).lower() == "true"
        with transaction.atomic():
            resultat = importer_depenses(uploaded, request.user, dry_run=dry_run)
            audit_import(request, resultat)
        return Response(resultat)
