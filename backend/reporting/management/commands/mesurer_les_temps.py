"""Temps de réponse des écrans lourds, sur une base jetable (décision 130).

    python manage.py mesurer_les_temps --base-jetable --compte rh.innov \\
        [--repetitions 20] [--simultanes 4] [--sortie mesures.json]

Chaque route est appelée dans le processus même (client de test de Django,
sans nginx ni gunicorn) : ce qui est mesuré, c'est la vue, ses requêtes SQL
et la sérialisation, sur le volume de la base. Avec ``--simultanes N``, N
appels tournent en même temps dans des fils du même processus, chacun avec
sa connexion à la base : comme les fils d'un worker gunicorn de la
production (``--worker-class gthread``, 2 workers × 4 fils), ils partagent
le verrou global de Python. Un écran qui calcule (l'export) ralentit alors
d'autant ses voisins ; un écran qui attend la base, beaucoup moins.

**Jamais sur la production.** Un export écrit au journal d'audit (une
donnée qui sort laisse une trace), une connexion écrit une session, et rien
ne se purge : la commande refuse de tourner sans ``--base-jetable``. Sa
place est la pile de « Restauration dans un environnement isolé »
(``deploy/README.md``), sur la copie de la nuit : le volume et le serveur
sont ceux de la production, la base ne l'est pas.
"""

import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test import Client

#: Les écrans qu'un utilisateur attend : nom lisible, chemin sous ``/api/``.
#: ``{annee}`` est l'exercice courant.
ROUTES = (
    ("Tableau de bord", "dashboard/?year={annee}"),
    ("Registre, première page", "expenses/"),
    ("Registre, recherche", "expenses/?search=a"),
    ("Dossiers", "dossiers/"),
    ("Projets", "projects/"),
    ("Journal d'audit", "audit/"),
    ("Synthèse de l'audit", "audit/synthese/"),
    ("Export xlsx de l'exercice", "exports/expenses.xlsx?year={annee}"),
)


def _hote() -> str:
    """Un hôte que la configuration accepte (sinon : 400 DisallowedHost)."""
    for hote in settings.ALLOWED_HOSTS:
        if hote != "*" and not hote.startswith("."):
            return hote
    return "testserver"


def _centile(valeurs: list[float], rang: int) -> float:
    if len(valeurs) == 1:
        return valeurs[0]
    return statistics.quantiles(valeurs, n=100, method="inclusive")[rang - 1]


class Command(BaseCommand):
    help = "Mesure les temps de réponse des écrans lourds sur une base jetable."

    def add_arguments(self, parser):
        parser.add_argument("--base-jetable", action="store_true", help="Confirme que la base est une copie jetable.")
        parser.add_argument("--compte", required=True, help="Identifiant d'un compte du siège (admin) de la base.")
        parser.add_argument("--repetitions", type=int, default=20)
        parser.add_argument("--simultanes", type=int, default=1)
        parser.add_argument("--sortie", help="Fichier JSON où écrire les mesures.")

    def handle(self, *args, **options):
        if not options["base_jetable"]:
            raise CommandError(
                "mesurer_les_temps écrit au journal d'audit (exports) et en session, "
                "et rien ne se purge : réservé à une base jetable. Relancez avec "
                "--base-jetable si c'est bien le cas."
            )
        repetitions, simultanes = options["repetitions"], options["simultanes"]
        if repetitions < 1 or simultanes < 1:
            raise CommandError("--repetitions et --simultanes valent au moins 1.")
        try:
            compte = get_user_model().objects.get(username=options["compte"], is_active=True)
        except get_user_model().DoesNotExist:
            raise CommandError(f"Aucun compte actif « {options['compte']} ».") from None

        hote, annee = _hote(), date.today().year

        def appel(chemin: str) -> tuple[float, int]:
            client = Client(SERVER_NAME=hote)
            client.force_login(compte)
            try:
                debut = time.perf_counter()
                reponse = client.get(f"/api/{chemin}", secure=True)
                return (time.perf_counter() - debut) * 1000, reponse.status_code
            finally:
                # Chaque fil a sa connexion : la rendre, ou Postgres les compte.
                connection.close()

        mesures = []
        self.stdout.write(f"{repetitions} appels par écran, {simultanes} à la fois, compte {compte.username}.")
        for nom, gabarit in ROUTES:
            chemin = gabarit.format(annee=annee)
            appel(chemin)  # un premier appel chauffe les caches de Django et de Postgres
            with ThreadPoolExecutor(max_workers=simultanes) as fils:
                resultats = list(fils.map(appel, [chemin] * repetitions))
            durees = sorted(duree for duree, _statut in resultats)
            statuts = sorted({statut for _duree, statut in resultats})
            ligne = {
                "ecran": nom,
                "chemin": f"/api/{chemin}",
                "statuts": statuts,
                "p50_ms": round(_centile(durees, 50), 1),
                "p95_ms": round(_centile(durees, 95), 1),
                "max_ms": round(durees[-1], 1),
            }
            mesures.append(ligne)
            alerte = "" if statuts == [200] else f"  ← statut {statuts}"
            self.stdout.write(
                f"{nom:<28} p50 {ligne['p50_ms']:>8.1f} ms   p95 {ligne['p95_ms']:>8.1f} ms   "
                f"max {ligne['max_ms']:>8.1f} ms{alerte}"
            )

        if options["sortie"]:
            with open(options["sortie"], "w", encoding="utf-8") as fichier:
                json.dump(
                    {"repetitions": repetitions, "simultanes": simultanes, "mesures": mesures},
                    fichier, ensure_ascii=False, indent=2,
                )
