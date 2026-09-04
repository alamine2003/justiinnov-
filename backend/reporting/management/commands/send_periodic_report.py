"""Envoi périodique du rapport de contrôle budgétaire (§5.7).

Exécutée par l'ordonnanceur (``manage.py run_scheduler``, conteneur
``scheduler``) : le lundi à 7 h pour l'hebdomadaire, le 1er du mois pour le
mensuel — cadences surchargeables par ``SCHEDULE_WEEKLY_REPORT`` et
``SCHEDULE_MONTHLY_REPORT``.

La commande est sans effet de bord destructeur : la relancer réenvoie le
rapport, elle ne modifie aucune donnée.

Chaque destinataire reçoit le rapport **de son périmètre**. Une direction
financière limitée au Togo recevait le classeur entier, dossiers ivoiriens
compris : le cloisonnement vérifié sur chaque requête était contourné par
un e-mail.

Le classeur joint n'est envoyé qu'aux administrateurs : seuls eux manipulent
des fichiers. Les autres destinataires reçoivent la synthèse dans le corps
du message et retrouvent le détail dans l'application. Chacun lit le
message dans sa langue.
"""

from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from accounts.models import Role
from accounts.permissions import EXPORT_ROLES, get_access
from budget.aggregates import consolidation_par_pays, current_rates
from expenses.models import Expense
from notifications.services import langue_de, recipients_for
from reporting import alerts as alert_rules
from reporting.exports import XLSX, build_reconciliation_workbook
from reporting.scope import querysets_pour

PERIODS = {"weekly": 7, "monthly": 30}

#: Libellé de chaque fenêtre, dans la langue du destinataire.
PERIOD_LABELS = {"weekly": gettext_lazy("hebdomadaire"), "monthly": gettext_lazy("mensuel")}

#: Destinataires du rapport : le siège — ceux qui pilotent (direction, RH)
#: et ceux qui contrôlent (DF, DM), chacun sur son périmètre.
AUDIENCE = [Role.SUPER_ADMIN, Role.ADMIN, Role.DF, Role.DM]


def _groupes_par_perimetre(users):
    """Regroupe les destinataires par (périmètre, pièce jointe, langue).

    Le périmètre est ``None`` pour le siège sans restriction, sinon les
    identifiants de pays visibles. Deux directions financières limitées aux
    mêmes pays reçoivent la même synthèse, construite une seule fois ; la
    pièce jointe et la langue séparent les groupes, car elles changent le
    message lui-même.
    """
    groupes = {}
    for user in users:
        access = get_access(user)
        if access is None:
            continue
        perimetre = None if access.has_global_scope else tuple(sorted(access.country_ids))
        cle = (perimetre, access.role in EXPORT_ROLES, langue_de(user))
        groupes.setdefault(cle, (access, []))[1].append(user)
    return groupes


class Command(BaseCommand):
    help = "Envoie le rapport de rapprochement aux responsables, chacun sur son périmètre."

    def add_arguments(self, parser):
        parser.add_argument(
            "--period", choices=sorted(PERIODS), default="weekly",
            help="Fenêtre couverte par le rapport.",
        )
        parser.add_argument(
            "--year", type=int, help="Année budgétaire (défaut : année courante)."
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Affiche les destinataires sans envoyer.",
        )

    def handle(self, *args, **options):
        period = options["period"]
        year = options["year"] or timezone.now().year
        since = timezone.now() - timedelta(days=PERIODS[period])

        recipients = [
            user for user in recipients_for(AUDIENCE).select_related("profile")
            if user.email
        ]
        groupes = _groupes_par_perimetre(recipients)

        if not groupes:
            # Sans adresse renseignée, l'envoi n'a personne à atteindre : le
            # dire vaut mieux que de terminer en silence.
            self.stdout.write(
                self.style.WARNING(
                    "Aucun destinataire avec adresse e-mail : rapport non envoyé."
                )
            )
            return

        envoyes = 0
        for (perimetre, avec_piece, langue), (access, users) in groupes.items():
            budgets, dossiers, _depenses = querysets_pour(access, year)
            with translation.override(langue):
                summary = self._summary(budgets, dossiers, since, year, period, avec_piece)
                sujet = _("[Contrôle budgétaire] Rapport %(period)s — %(year)s") % {
                    "period": PERIOD_LABELS[period], "year": year,
                }
            libelle = (
                "siège (tous pays)" if perimetre is None else f"pays {list(perimetre)}"
            )

            if options["dry_run"]:
                self.stdout.write(f"--- Périmètre : {libelle} ({langue})")
                self.stdout.write(summary)
                self.stdout.write(
                    "Destinataires : " + ", ".join(u.email for u in users)
                )
                continue

            message = EmailMessage(
                subject=sujet,
                body=summary,
                from_email=settings.DEFAULT_FROM_EMAIL,
                # En copie cachée : les destinataires n'ont pas à connaître
                # les adresses les uns des autres.
                bcc=[user.email for user in users],
            )
            if avec_piece:
                message.attach(
                    f"rapprochement-{year}.xlsx",
                    build_reconciliation_workbook(budgets, dossiers),
                    XLSX,
                )
            message.send()
            envoyes += len(users)

        if options["dry_run"]:
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Rapport envoyé à {envoyes} destinataire(s), "
                f"{len(groupes)} périmètre(s)."
            )
        )

    def _summary(self, budgets, dossiers, since, year, period, avec_piece):
        """Corps du message : l'essentiel se lit sans ouvrir la pièce jointe.

        Les montants ne s'additionnent que par pays, chacun dans sa devise ;
        le seul total est le consolidé en FCFA, les devises sans taux étant
        nommées plutôt qu'absorbées.
        """
        rows, consolide = consolidation_par_pays(budgets, rates=current_rates())
        lignes_pays = [
            _(
                "- %(country)s (%(currency)s) : attribué %(allocated)s, "
                "consommé %(consumed)s, justifié %(justified)s, écart %(gap)s"
            ) % {
                "country": row["country_name"], "currency": row["currency"],
                "allocated": row["allocated"], "consumed": row["consumed"],
                "justified": row["justified"], "gap": row["gap"],
            }
            for row in rows
        ] or [_("- aucune enveloppe sur le périmètre")]

        nouvelles = Expense.objects.filter(
            created_at__gte=since, country__in=dossiers.values("country")
        ).count()
        # Même règle que l'alerte « justificatif manquant » : les brouillons
        # ne comptent pas, une pièce rejetée ou archivée ne couvre rien.
        sans_preuve = sum(
            1 for alerte in alert_rules.proof_alerts(dossiers)
            if alerte["kind"] == "proof_missing"
        )
        non_converties = consolide["unconverted_currencies"]

        return (
            _("Rapport %(period)s — exercice %(year)s") % {
                "period": PERIOD_LABELS[period], "year": year,
            }
            + "\n"
            + _("Période couverte : depuis le %(since)s") % {"since": since.date().isoformat()}
            + "\n\n"
            + _("Par pays, dans la devise du pays :") + "\n"
            + "\n".join(lignes_pays)
            + "\n\n" + _("Consolidé en FCFA :") + "\n"
            + _("Enveloppes attribuées : %(amount)s") % {"amount": consolide["allocated"]} + "\n"
            + _("Consommé : %(amount)s") % {"amount": consolide["consumed"]} + "\n"
            + _("Justifié : %(amount)s") % {"amount": consolide["justified"]} + "\n"
            + _("Écart (dépensé sans preuve) : %(amount)s") % {
                "amount": consolide["consumed"] - consolide["justified"]
            } + "\n"
            + (
                _("Hors consolidation, faute de taux : %(currencies)s") % {
                    "currencies": ", ".join(non_converties)
                } + "\n"
                if non_converties else ""
            )
            + "\n" + _("Dépenses saisies sur la période : %(count)s") % {"count": nouvelles} + "\n"
            + _("Dossiers sans aucun justificatif : %(count)s") % {"count": sans_preuve} + "\n\n"
            + (
                _("Le détail par enveloppe et par dossier figure en pièce jointe.")
                if avec_piece
                else _("Le détail par enveloppe et par dossier se consulte dans l'application.")
            )
        )
