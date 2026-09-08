"""Enveloppes désactivées qui portent pourtant des dépenses déclarées.

Depuis l'audit du 8 septembre 2026 (§4.2), une enveloppe ne se désactive
plus tant qu'elle porte des lignes déclarées : désactivée, elle sort du
suivi (``reporting.scope``) et son consommé disparaît du tableau de bord,
des exports et des alertes — alors que les mêmes lignes restent comptées
dans la répartition par équipe ou par projet. Deux écrans, deux chiffres.

**Interdire les nouvelles désactivations ne corrige pas celles qui
existent.** Cette commande les liste, avec ce qu'elles font disparaître,
sans rien modifier : la remise en service est une décision — réactiver
l'enveloppe (les chiffres du pays remonteront) ou constater que la
désactivation était juste et que les lignes doivent être rouvertes puis
réimputées. À jouer avant l'ouverture aux filiales, puis à chaque clôture
d'exercice.

    manage.py enveloppes_desactivees
    manage.py enveloppes_desactivees --annee 2026
"""

from django.core.management.base import BaseCommand

from budget.aggregates import consumption
from budget.models import Budget
from core.statuts import Status


class Command(BaseCommand):
    help = "Liste les enveloppes désactivées portant des dépenses déclarées (sans rien modifier)."

    def add_arguments(self, parser):
        parser.add_argument("--annee", type=int, help="Restreint à un exercice.")

    def handle(self, *args, **options):
        enveloppes = (
            Budget.objects.filter(is_active=False)
            .select_related("country", "project", "team", "manager")
            .order_by("country__name", "year")
        )
        if options["annee"]:
            enveloppes = enveloppes.filter(year=options["annee"])

        trouvees = []
        for enveloppe in enveloppes:
            declarees = enveloppe.expenses.exclude(status=Status.DRAFT).count()
            if declarees:
                trouvees.append((enveloppe, declarees, consumption(enveloppe)))

        if not trouvees:
            self.stdout.write("Aucune enveloppe désactivée ne porte de dépense déclarée.")
            return

        for enveloppe, declarees, totaux in trouvees:
            self.stdout.write(
                f"{enveloppe.country.code} {enveloppe.year} · {enveloppe} · "
                f"{declarees} ligne(s) déclarée(s)"
            )
            self.stdout.write(
                f"    invisibles dans les totaux : engagé {totaux['engaged']}, "
                f"consommé {totaux['consumed']}, justifié {totaux['justified']} "
                f"{enveloppe.country.currency}"
            )
        self.stdout.write(
            self.style.WARNING(
                f"{len(trouvees)} enveloppe(s) désactivée(s) font disparaître des "
                "dépenses déclarées des totaux. Réactiver (les chiffres du pays "
                "remonteront) ou rouvrir les dossiers concernés — décision à "
                "prendre et à consigner, jamais un effet de bord."
            )
        )
