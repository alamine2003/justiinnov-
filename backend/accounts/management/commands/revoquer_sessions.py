"""Révoque les sessions : tous les jetons d'API, ou ceux d'un compte.

Un jeton DRF vaut porteur jusqu'à ``TOKEN_MAX_AGE_DAYS`` (30 jours) : un
jeton lu dans une sauvegarde, sur un poste perdu ou dans un journal reste
valable jusque-là. Cette commande le retire ; la prochaine requête devra
se reconnecter (mot de passe et, pour un compte enrôlé, second facteur).

    manage.py revoquer_sessions --tous --motif "fuite de sauvegarde"
    manage.py revoquer_sessions --compte alamine.innov --motif "poste perdu"

Chaque compte touché reçoit une entrée d'historique (``ChangeLog``,
action « déconnexion », famille « session ») portant le motif : révoquer
est un acte d'administration, il se relit.

Ce que la révocation d'un jeton ne fait **pas** : elle ne change ni le mot
de passe ni le secret TOTP. Une sauvegarde ou une base lue par un tiers
livre aussi les secrets TOTP en clair : après une telle fuite, chaque
compte enrôlé doit être réenrôlé (``reset-2fa`` par un administrateur,
puis enrôlement par le titulaire), et les mots de passe réinitialisés.
Voir deploy/README.md, « Après une fuite ».
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework.authtoken.models import Token

from accounts.journal import journaliser_compte
from core.journal import Trace
from core.models import ChangeLog


class Command(BaseCommand):
    help = "Révoque les jetons d'API : de tous les comptes (--tous) ou d'un compte (--compte)."

    def add_arguments(self, parser):
        cible = parser.add_mutually_exclusive_group(required=True)
        cible.add_argument("--tous", action="store_true", help="Tous les comptes.")
        cible.add_argument("--compte", help="Nom d'un compte.")
        parser.add_argument(
            "--motif", required=True,
            help="Pourquoi : inscrit dans l'historique de chaque compte touché.",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Dit ce qui serait révoqué, sans le faire.",
        )

    def handle(self, *args, **options):
        motif = options["motif"].strip()
        if not motif:
            raise CommandError("Le motif ne peut pas être vide.")
        jetons = Token.objects.select_related("user")
        if options["compte"]:
            if not User.objects.filter(username=options["compte"]).exists():
                raise CommandError(f"Compte inconnu : {options['compte']}")
            jetons = jetons.filter(user__username=options["compte"])
        comptes = [jeton.user for jeton in jetons]
        if not comptes:
            self.stdout.write("Aucune session à révoquer.")
            return
        for user in comptes:
            self.stdout.write(f"  {user.username}")
        if options["dry_run"]:
            self.stdout.write(f"{len(comptes)} session(s) seraient révoquée(s) (simulation).")
            return

        trace = Trace(user="(commande revoquer_sessions)")
        with transaction.atomic():
            for user in comptes:
                Token.objects.filter(user=user).delete()
                journaliser_compte(
                    trace, user, ChangeLog.Actions.LOGOUT,
                    changed_fields=["token"],
                    diff={"motif": [None, motif], "par": [None, "revoquer_sessions"]},
                )
        self.stdout.write(self.style.SUCCESS(f"✔ {len(comptes)} session(s) révoquée(s) : {motif}"))
