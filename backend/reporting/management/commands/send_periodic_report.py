"""Envoi périodique du rapport de contrôle budgétaire (§5.7).

Exécutée par l'ordonnanceur (``manage.py run_scheduler``, conteneur
``scheduler``) : le lundi à 7 h pour l'hebdomadaire, le 1er du mois pour le
mensuel — cadences surchargeables par ``SCHEDULE_WEEKLY_REPORT`` et
``SCHEDULE_MONTHLY_REPORT``.

La commande est sans effet de bord destructeur : la relancer réenvoie le
rapport, elle ne modifie aucune donnée.

Chaque destinataire reçoit le rapport **de son périmètre**. Un contrôleur
limité au Togo recevait le classeur entier, dossiers ivoiriens compris : le
cloisonnement vérifié sur chaque requête était contourné par un e-mail.
"""

from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Role
from accounts.permissions import get_access
from budget.aggregates import consolidation_par_pays, current_rates
from expenses.models import Expense
from notifications.services import recipients_for
from reporting import alerts as alert_rules
from reporting.exports import build_reconciliation_workbook
from reporting.scope import querysets_pour

PERIODS = {"weekly": 7, "monthly": 30}

#: Destinataires du rapport : ceux qui pilotent et ceux qui contrôlent.
AUDIENCE = [Role.SUPER_ADMIN, Role.DOO, Role.CONTROLLER, Role.AUDITOR]

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _groupes_par_perimetre(users):
    """Regroupe les destinataires par périmètre : un rapport par périmètre.

    La clé est ``None`` pour le siège sans restriction, sinon les identifiants
    de pays visibles. Deux contrôleurs limités aux mêmes pays reçoivent le
    même classeur, construit une seule fois.
    """
    groupes = {}
    for user in users:
        access = get_access(user)
        if access is None:
            continue
        cle = None if access.has_global_scope else tuple(sorted(access.country_ids))
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
        for cle, (access, users) in groupes.items():
            budgets, dossiers, _ = querysets_pour(access, year)
            summary = self._summary(budgets, dossiers, since, year, period)
            perimetre = "siège (tous pays)" if cle is None else f"pays {list(cle)}"

            if options["dry_run"]:
                self.stdout.write(f"--- Périmètre : {perimetre}")
                self.stdout.write(summary)
                self.stdout.write(
                    "Destinataires : " + ", ".join(u.email for u in users)
                )
                continue

            message = EmailMessage(
                subject=f"[Contrôle budgétaire] Rapport {period} — {year}",
                body=summary,
                from_email=settings.DEFAULT_FROM_EMAIL,
                # En copie cachée : les destinataires n'ont pas à connaître
                # les adresses les uns des autres.
                bcc=[user.email for user in users],
            )
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

    def _summary(self, budgets, dossiers, since, year, period):
        """Corps du message : l'essentiel se lit sans ouvrir la pièce jointe.

        Les montants ne s'additionnent que par pays, chacun dans sa devise ;
        le seul total est le consolidé en FCFA, les devises sans taux étant
        nommées plutôt qu'absorbées.
        """
        rows, consolide = consolidation_par_pays(budgets, rates=current_rates())
        lignes_pays = [
            f"- {row['country_name']} ({row['currency']}) : attribué "
            f"{row['allocated']}, consommé {row['consumed']}, justifié "
            f"{row['justified']}, écart {row['gap']}"
            for row in rows
        ] or ["- aucune enveloppe sur le périmètre"]

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
            f"Rapport {period} — exercice {year}\n"
            f"Période couverte : depuis le {since.date().isoformat()}\n\n"
            "Par pays, dans la devise du pays :\n"
            + "\n".join(lignes_pays)
            + "\n\nConsolidé en FCFA :\n"
            f"Enveloppes attribuées : {consolide['allocated']}\n"
            f"Consommé : {consolide['consumed']}\n"
            f"Justifié : {consolide['justified']}\n"
            f"Écart (dépensé sans preuve) : {consolide['consumed'] - consolide['justified']}\n"
            + (
                f"Hors consolidation, faute de taux : {', '.join(non_converties)}\n"
                if non_converties else ""
            )
            + f"\nDépenses saisies sur la période : {nouvelles}\n"
            f"Dossiers sans aucun justificatif : {sans_preuve}\n\n"
            "Le détail par enveloppe et par dossier figure en pièce jointe."
        )
