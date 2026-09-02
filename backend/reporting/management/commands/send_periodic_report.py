"""Envoi périodique du rapport de contrôle budgétaire (§5.7).

À planifier sur l'hôte, par exemple chaque lundi à 7 h :

    0 7 * * 1  docker compose exec -T backend \
                 python manage.py send_periodic_report --period=weekly

La commande est sans effet de bord destructeur : la relancer réenvoie le
rapport, elle ne modifie aucune donnée.
"""

from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Role
from budget.models import Budget
from expenses.models import Dossier, Expense
from notifications.services import recipients_for
from reporting.exports import build_reconciliation_workbook

PERIODS = {"weekly": 7, "monthly": 30}

#: Destinataires du rapport : ceux qui pilotent et ceux qui contrôlent.
AUDIENCE = [Role.SUPER_ADMIN, Role.DOO, Role.CONTROLLER, Role.AUDITOR]

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class Command(BaseCommand):
    help = "Envoie le rapport de rapprochement aux responsables."

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

        budgets = Budget.objects.filter(year=year).select_related(
            "country", "project", "team", "manager"
        ).with_consumption()
        dossiers = Dossier.objects.filter(date__year=year).select_related("country")

        recipients = [
            user for user in recipients_for(AUDIENCE) if user.email
        ]
        summary = self._summary(budgets, dossiers, since, year, period)

        if options["dry_run"]:
            self.stdout.write(summary)
            self.stdout.write(
                "Destinataires : "
                + (", ".join(u.email for u in recipients) or "aucun")
            )
            return

        if not recipients:
            # Sans adresse renseignée, l'envoi n'a personne à atteindre : le
            # dire vaut mieux que de terminer en silence.
            self.stdout.write(
                self.style.WARNING(
                    "Aucun destinataire avec adresse e-mail : rapport non envoyé."
                )
            )
            return

        message = EmailMessage(
            subject=f"[Contrôle budgétaire] Rapport {period} — {year}",
            body=summary,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email for user in recipients],
        )
        message.attach(
            f"rapprochement-{year}.xlsx",
            build_reconciliation_workbook(budgets, dossiers),
            XLSX,
        )
        message.send()

        self.stdout.write(
            self.style.SUCCESS(f"Rapport envoyé à {len(recipients)} destinataire(s).")
        )

    def _summary(self, budgets, dossiers, since, year, period):
        """Corps du message : l'essentiel se lit sans ouvrir la pièce jointe."""
        from budget.aggregates import budget_figures

        alloue = consomme = justifie = 0
        for budget in budgets:
            figures = budget_figures(budget)
            if budget.scope_kind == "country":
                alloue += budget.amount
            consomme += figures["consumed"]
            justifie += figures["justified"]

        nouvelles = Expense.objects.filter(created_at__gte=since).count()
        sans_preuve = dossiers.filter(proofs__isnull=True).distinct().count()

        return (
            f"Rapport {period} — exercice {year}\n"
            f"Période couverte : depuis le {since.date().isoformat()}\n\n"
            f"Enveloppes attribuées : {alloue}\n"
            f"Consommé : {consomme}\n"
            f"Justifié : {justifie}\n"
            f"Écart (dépensé sans preuve) : {consomme - justifie}\n\n"
            f"Dépenses saisies sur la période : {nouvelles}\n"
            f"Dossiers sans aucun justificatif : {sans_preuve}\n\n"
            "Le détail par enveloppe et par dossier figure en pièce jointe."
        )
