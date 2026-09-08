"""Inventaire des lignes en double d'un même dossier — sans rien supprimer.

Avant la contrainte ``ligne_importee_unique_par_dossier`` (migration
0014), deux imports simultanés du même classeur écrivaient toutes les
lignes deux fois. Rien ne distingue, après coup, une ligne importée d'une
ligne saisie : cette commande liste les groupes de lignes **en brouillon**
d'un même dossier qui portent le même jour, le même libellé et le même
montant, avec leurs identifiants et leur auteur, pour qu'un humain tranche.
Deux dépenses saisies identiques sont deux dépenses ; un doublon d'import
se retire par son auteur, depuis l'application (le brouillon d'une ligne,
par celui qui l'a importée), jamais d'ici.

    manage.py doublons_importes            # tout
    manage.py doublons_importes --pays TG  # un pays
"""

from collections import defaultdict
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand
from django.utils import timezone

from expenses.models import Expense
from expenses.workflow import Status


def fuseau_de(country):
    """Fuseau du pays, UTC s'il est illisible — comme ``expenses.services``."""
    try:
        return ZoneInfo(country.timezone or "UTC")
    except Exception:
        return ZoneInfo("UTC")


class Command(BaseCommand):
    help = "Liste les lignes en brouillon en double dans un même dossier (sans rien supprimer)."

    def add_arguments(self, parser):
        parser.add_argument("--pays", help="Code ISO du pays (TG, CI…), sinon tous.")

    def handle(self, *args, **options):
        lignes = Expense.objects.filter(status=Status.DRAFT).select_related(
            "dossier", "country"
        ).order_by("dossier_id", "pk")
        if options["pays"]:
            lignes = lignes.filter(country__code=options["pays"].upper())
        groupes = defaultdict(list)
        for ligne in lignes:
            jour = timezone.localtime(ligne.date, fuseau_de(ligne.country)).date()
            groupes[(ligne.dossier_id, jour, ligne.title, ligne.amount)].append(ligne)
        doublons = {cle: lot for cle, lot in groupes.items() if len(lot) > 1}
        if not doublons:
            self.stdout.write("Aucun doublon en brouillon.")
            return
        for (dossier_id, jour, title, amount), lot in sorted(doublons.items()):
            dossier = lot[0].dossier
            self.stdout.write(
                f"{dossier.country.code} {dossier.number} · {jour} · {title[:60]} · {amount} : "
                f"{len(lot)} lignes"
            )
            for ligne in lot:
                cle = "importée" if ligne.import_key else "origine inconnue"
                self.stdout.write(
                    f"    id {ligne.pk} · saisie par {ligne.created_by or '?'} le "
                    f"{timezone.localtime(ligne.created_at).strftime('%d/%m/%Y %H:%M')} · {cle}"
                )
        self.stdout.write(
            self.style.WARNING(
                f"{len(doublons)} groupe(s) de doublons : à trancher par un humain — un "
                "brouillon se retire par son auteur, depuis l'application."
            )
        )
