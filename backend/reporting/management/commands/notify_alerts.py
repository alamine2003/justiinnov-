"""Émission des notifications d'alerte (§8).

Les alertes sont *calculées* à chaque lecture du tableau de bord ; leur
*notification* passe par ici. Séparer les deux évite qu'une requête de lecture
écrive en base, et surtout que l'alerte dépende de quelqu'un qui regarde : sans
cette commande, un dépassement survenu un dimanche n'avertirait personne.

Elle est exécutée par l'ordonnanceur (``manage.py run_scheduler``, conteneur
``scheduler``), toutes les heures par défaut — cadence surchargeable par la
variable ``SCHEDULE_ALERTS``.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.permissions import Access
from accounts.models import Role
from core.models import Country
from notifications import triggers
from reporting import alerts as alert_rules
from reporting.scope import bornes_annee, querysets_pour

#: Droits de la commande : elle voit tout, comme le siège.
SIEGE = Access(role=Role.SUPER_ADMIN, country_ids=None)


class Command(BaseCommand):
    help = "Calcule les alertes en cours et notifie les personnes concernées."

    def add_arguments(self, parser):
        parser.add_argument(
            "--year", type=int, help="Année budgétaire (défaut : année courante)."
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Affiche les alertes sans notifier personne.",
        )

    def handle(self, *args, **options):
        annee_explicite = options["year"] is not None
        year = options["year"] or timezone.now().year

        budgets, dossiers, expenses = querysets_pour(SIEGE, year)
        if not annee_explicite and timezone.now().month == 1:
            # En janvier, les dossiers de décembre encore sans preuve sont
            # ceux qui pressent le plus ; borner à l'année civile courante les
            # ferait taire précisément au moment où le rappel compte. Sans
            # ``--year``, la commande couvre donc aussi l'exercice précédent ;
            # les dossiers clôturés en sont écartés par la règle elle-même.
            debut, _ = bornes_annee(year - 1)[0]
            _, fin = bornes_annee(year)[0]
            dossiers = querysets_pour(SIEGE)[1].filter(date__range=(debut, fin))

        current = alert_rules.collect(budgets, dossiers, expenses)
        notifiables = [a for a in current if a["kind"] in triggers.ALERT_KINDS]

        if not notifiables:
            self.stdout.write("Aucune alerte à notifier.")
            return

        # Les pays sont chargés en une fois : les résoudre alerte par alerte
        # multiplierait les requêtes par le nombre d'alertes.
        pays = {
            country.pk: country
            for country in Country.objects.filter(
                pk__in={a["country"] for a in notifiables if a["country"]}
            )
        }

        # Les destinataires sont résolus une fois par (type d'alerte, pays) :
        # cent dossiers sans preuve interrogeaient sinon cent fois la même
        # liste.
        destinataires = {}
        emises = 0

        for alerte in notifiables:
            country = pays.get(alerte["country"])
            if country is None:
                continue
            if options["dry_run"]:
                self.stdout.write(f"  [{alerte['level']}] {alerte['title']}")
                continue

            cle = (alerte["kind"], country.pk)
            if cle not in destinataires:
                destinataires[cle] = triggers.audience_for(alerte["kind"], country)
            emises += len(
                triggers.alert_raised(alerte, country, destinataires[cle])
            )

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"\nSimulation : {len(notifiables)} alerte(s), rien envoyé."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(notifiables)} alerte(s) examinée(s), "
                f"{emises} notification(s) émise(s)."
            )
        )
