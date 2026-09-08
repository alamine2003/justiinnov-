"""Consolidation d'un exercice en FCFA — au taux de référence, ou revalorisée.

Les écrans et l'API consolident un exercice **à sa date de référence**
(``budget.aggregates.date_de_reference`` : sa clôture, ou ce jour) : un
exercice clos ne bouge plus. Relire un exercice clos aux taux d'aujourd'hui
est une **revalorisation** — un autre chiffre, qui répond à une autre
question (« que vaudraient ces enveloppes aujourd'hui ? ») et ne doit
jamais se confondre avec le rapport historique. Elle se demande ici,
explicitement, et se lit avec sa date de taux en tête de sortie.

    manage.py consolidation --annee 2025               # taux au 31/12/2025
    manage.py consolidation --annee 2025 --taux-du-jour # revalorisation
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Role
from accounts.permissions import Access
from budget.aggregates import consolidation_par_pays, current_rates, date_de_reference
from reporting.scope import querysets_pour

SIEGE = Access(role=Role.SUPER_ADMIN, country_ids=None)


class Command(BaseCommand):
    help = "Consolide un exercice en FCFA, à sa date de référence ou revalorisé aux taux du jour."

    def add_arguments(self, parser):
        parser.add_argument("--annee", type=int, help="Exercice (défaut : année en cours).")
        parser.add_argument(
            "--taux-du-jour", action="store_true",
            help="Revalorisation : taux en vigueur aujourd'hui, pas à la clôture de l'exercice.",
        )

    def handle(self, *args, **options):
        annee = options["annee"] or timezone.now().year
        date_taux = timezone.localdate() if options["taux_du_jour"] else date_de_reference(annee)
        budgets, _, _ = querysets_pour(SIEGE, annee)
        rows, consolide = consolidation_par_pays(budgets, rates=current_rates(on_date=date_taux))

        nature = "REVALORISATION aux taux du jour" if options["taux_du_jour"] else "rapport historique"
        self.stdout.write(f"Exercice {annee} — {nature} — taux en vigueur au {date_taux:%d/%m/%Y}")
        self.stdout.write(f"{'Pays':<24} {'Devise':<7} {'Attribué':>16} {'Consommé':>16} {'Justifié':>16} {'Disponible':>16} {'Disponible XOF':>18}")
        for row in rows:
            self.stdout.write(
                f"{row['country_name'][:24]:<24} {row['currency']:<7} {row['allocated']:>16} "
                f"{row['consumed']:>16} {row['justified']:>16} {row['remaining']:>16} "
                f"{str(row['remaining_xof']) if row['remaining_xof'] is not None else 'sans taux':>18}"
            )
        self.stdout.write(
            f"{'TOTAL FCFA':<32} {consolide['allocated']:>16} {consolide['consumed']:>16} "
            f"{consolide['justified']:>16} {consolide['remaining']:>16}"
        )
        if consolide["unconverted_currencies"]:
            self.stdout.write(
                self.style.WARNING(
                    "Devises sans taux, hors du total : "
                    + ", ".join(consolide["unconverted_currencies"])
                )
            )
