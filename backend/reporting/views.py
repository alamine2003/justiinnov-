"""Tableaux de bord temps réel (§5.6) et exports (§5.7)."""

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import FormParser, MultiPartParser

from budget.aggregates import consolidation_par_pays, current_rates, to_xof
from core.journal import tracer
from core.models import Country
from expenses.models import AuditLog
from expenses.workflow import CONSUMING_STATUSES, ENGAGING_STATUSES, Status

from . import alerts as alert_rules
from .exports import (
    FORMATS,
    PDF,
    build_country_report_pdf,
    lignes_depenses,
    tableaux_rapprochement,
)
from .scope import Periode, fuseau_de, scoped_querysets
from accounts.permissions import EXPORT_ROLES, RolePermission, get_access
from .imports import audit_import, importer_depenses
from .serializers import (
    BreakdownSerializer,
    DashboardSerializer,
    ImportSerializer,
    ImportResultSerializer,
)

#: Paramètres communs du pilotage et des exports, pour le schéma.
PARAMETRE_ANNEE = OpenApiParameter(
    "year", int, description="Exercice ; l'année en cours par défaut."
)
PARAMETRE_MOIS = OpenApiParameter(
    "month", int, description="Mois (1-12) ; sans lui, l'exercice entier."
)
PARAMETRE_PAYS = OpenApiParameter(
    "country", int,
    description="Pays ; un pays inconnu ou hors périmètre répond 404.",
)

ZERO = Decimal("0.00")

#: Nombre d'alertes transmises au tableau de bord, les plus graves d'abord.
MAX_ALERTS = 50


def _as_int(value, field):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError({field: _("Valeur entière attendue.")})


def _mois(value):
    """Mois optionnel de la requête, entre 1 et 12."""
    month = _as_int(value, "month")
    if month is not None and not 1 <= month <= 12:
        raise ValidationError({"month": _("Le mois doit être compris entre 1 et 12.")})
    return month


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

    @extend_schema(parameters=[PARAMETRE_ANNEE, PARAMETRE_PAYS], responses=DashboardSerializer)
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
                "alerts": [alert_rules.rendue(a) for a in current_alerts[:MAX_ALERTS]],
                "alerts_total": len(current_alerts),
            }
        )

    #: Chiffres d'une ligne de pays qui se consolident en FCFA.
    MONTANTS = ("allocated", "engaged", "consumed", "justified", "remaining")

    def _totaux_consolides(self, rows):
        """Totaux globaux, en FCFA uniquement.

        Additionner « allocated » du Togo (XOF) et du Guinée (GNF) donnait un
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

    @extend_schema(parameters=[PARAMETRE_ANNEE, PARAMETRE_PAYS], responses=BreakdownSerializer)
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
            raise ValidationError({"country": _("Le pays est obligatoire.")})
        expenses = scoped_querysets(request, year, country_id)[2]
        # Le pays est obligatoire, donc son fuseau est connu : les lignes
        # sont bornées et réparties par mois à l'heure du pays, pas à celle
        # du serveur. ``scoped_querysets`` a déjà refusé un pays inconnu.
        fuseau = fuseau_de(Country.objects.get(pk=country_id))

        # Brouillons et refus ne représentent aucune consommation réelle.
        counted = expenses.filter(
            status__in=list(ENGAGING_STATUSES) + list(CONSUMING_STATUSES)
        )
        return Response(
            {
                "year": year,
                "by_team": self._group(counted, "team__name", _("Sans équipe")),
                "by_owner": self._group(counted, "owner__name", _("Sans propriétaire")),
                "by_project": self._group(counted, "project__name", _("Hors projet")),
                "by_category": self._group(
                    counted, "marketing_category__name", _("Sans catégorie")
                ),
                "by_expense_title": self._group(
                    counted, "expense_title__label", _("Sans intitulé")
                ),
                "by_month": self._by_month(counted, fuseau),
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

    def _by_month(self, expenses, fuseau):
        rows = (
            expenses.annotate(month=TruncMonth("date", tzinfo=fuseau))
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
    """Base des exports : réservés aux administrateurs, périmètre appliqué,
    période choisie, téléchargement tracé.

    Seuls les administrateurs manipulent des fichiers ; le reste de
    l'organisation travaille dans l'application. La lecture est donc
    refusée, pas seulement l'écriture : un export **est** une sortie de
    données.

    ``year`` et ``month`` (1–12, facultatif) bornent dossiers et dépenses ;
    sans mois, l'exercice entier. Le format est choisi par la route
    (``export_format``), le nom du fichier porte la période.
    """

    permission_classes = [RolePermission]
    read_roles = EXPORT_ROLES

    #: Radical du nom de fichier et libellé d'audit, par vue. Le libellé
    #: d'audit reste en français : le journal se relit tel qu'il a été
    #: écrit, quelle que soit la langue de qui le consulte.
    prefix = "export"
    audit_label = "Export"
    #: Titre du document produit, dans la langue de l'utilisateur.
    titre = gettext_lazy("Export")
    #: « xlsx », « csv », « docx » ou « pdf », posé par la route.
    export_format = "xlsx"

    def build(self, budgets, dossiers, expenses, periode, country_id):  # pragma: no cover
        raise NotImplementedError

    @extend_schema(
        parameters=[PARAMETRE_ANNEE, PARAMETRE_MOIS, PARAMETRE_PAYS],
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def get(self, request):
        year = _as_int(request.query_params.get("year"), "year") or timezone.now().year
        month = _mois(request.query_params.get("month"))
        country_id = _as_int(request.query_params.get("country"), "country")
        periode = Periode(year, month)
        # Le pays est vérifié contre le périmètre par ``scoped_querysets`` :
        # un identifiant inconnu ou étranger répond 404 avant tout calcul.
        budgets, dossiers, expenses = scoped_querysets(request, year, country_id, month)

        # La période validée sert aussi au nom du fichier : reprise brute de
        # la requête, elle y injectait ce que le client voulait.
        content, content_type = self.build(budgets, dossiers, expenses, periode, country_id)
        filename = f"{self.prefix}-{periode.suffixe}.{self.export_format}"
        self._audit(request, periode, country_id, filename)

        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def _contexte(self, periode, country_id):
        """En-tête du document Word : pays, exercice, période."""
        pays = Country.objects.filter(pk=country_id).first() if country_id else None
        return {
            "titre": f"{self.titre} — {periode.libelle}",
            "pays": pays.name if pays else _("Tous les pays du périmètre"),
            "exercice": periode.year,
            "periode": periode.libelle,
        }

    def _tabulaire(self, tableaux, periode, country_id):
        """Écrit les tableaux dans le format de la route."""
        ecrire, content_type = FORMATS[self.export_format]
        return ecrire(tableaux, self._contexte(periode, country_id)), content_type

    def _audit(self, request, periode, country_id, filename):
        """Un export sort des données du système : il laisse une trace."""
        tracer(
            request,
            AuditLog.Action.DOWNLOADED,
            "Export",
            famille="export",
            label=f"{self.audit_label} — {filename}",
            country=country_id,
            detail={
                "year": periode.year,
                "month": periode.month,
                "country": country_id,
                "format": self.export_format,
            },
        )


class ExpensesExportView(ExportView):
    """Export des dépenses au format du fichier historique (xlsx, csv, docx)."""

    prefix = "depenses"
    audit_label = "Export des dépenses"
    titre = gettext_lazy("Export des dépenses")

    def build(self, budgets, dossiers, expenses, periode, country_id):
        # Les lignes, pas les dossiers : une ligne se classe par sa propre
        # date, bornée dans le fuseau de son pays par ``scoped_querysets``.
        return self._tabulaire([lignes_depenses(expenses)], periode, country_id)


class ReconciliationExportView(ExportView):
    """Rapprochement dépenses / montants justifiés (§5.7), xlsx, csv ou docx."""

    prefix = "rapprochement"
    audit_label = "Rapport de rapprochement"
    titre = gettext_lazy("Rapport de rapprochement")

    def build(self, budgets, dossiers, expenses, periode, country_id):
        return self._tabulaire(
            tableaux_rapprochement(budgets, dossiers), periode, country_id
        )


class CountryReportView(ExportView):
    """Rapport PDF par pays et période."""

    prefix = "rapport"
    audit_label = "Rapport PDF"
    titre = gettext_lazy("Rapport PDF")
    export_format = "pdf"

    def build(self, budgets, dossiers, expenses, periode, country_id):
        return build_country_report_pdf(budgets, dossiers, expenses, periode), PDF


class ExpensesImportView(APIView):
    """Importe l'export des dépenses ou le classeur historique du client.

    Réservé aux administrateurs, comme les exports : seuls eux manipulent
    des fichiers. Le pays déclare dans l'application, ligne à ligne ; ce qui
    entre par un classeur arrive en brouillon et suit ensuite le même
    circuit.

    Le classeur historique est mono-pays et n'a pas de colonne PAYS : le
    pays vient alors du paramètre ``country`` (requête ou formulaire),
    vérifié contre le périmètre du demandeur.
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [RolePermission]
    write_roles = EXPORT_ROLES

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "dry_run", bool,
                description="Valide le classeur sans rien écrire.",
            ),
            PARAMETRE_PAYS,
        ],
        request={"multipart/form-data": ImportSerializer},
        responses=ImportResultSerializer,
    )
    def post(self, request):
        self.check_permissions(request)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise ValidationError({"file": _("Le champ file est obligatoire.")})
        dry_run = str(request.query_params.get("dry_run", "false")).lower() == "true"
        country = self._pays_de_l_import(request)
        with transaction.atomic():
            resultat = importer_depenses(
                uploaded, request.user, dry_run=dry_run, country=country
            )
            audit_import(request, resultat, country=country)
        return Response(resultat)

    def _pays_de_l_import(self, request):
        """Le pays désigné par la requête, s'il est dans le périmètre.

        Un pays inconnu et un pays hors périmètre reçoivent le même refus :
        dire « hors périmètre » confirmerait qu'il existe.
        """
        brut = request.query_params.get("country") or request.data.get("country")
        if brut in (None, ""):
            return None
        country_id = _as_int(brut, "country")
        access = get_access(request.user)
        candidats = Country.objects.filter(pk=country_id)
        if not access.has_global_scope:
            candidats = candidats.filter(pk__in=access.country_ids)
        country = candidats.first()
        if country is None:
            raise ValidationError({"country": _("Pays inconnu.")})
        return country
