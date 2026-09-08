"""Contrôle d'une base restaurée : ce qu'elle contient, et si les pièces sont là.

Une sauvegarde copiée n'est pas une sauvegarde restaurée. Après
``deploy/restaurer.sh`` dans un environnement **isolé** (base jetable,
bucket jetable, courrier en console), cette commande lit la base et le
stockage qu'on lui donne et dit, sans rien écrire :

- combien de comptes, de pays, de dossiers, de lignes, d'entrées d'audit
  et d'historique — et la date de la dernière entrée d'audit, qui est la
  perte de données réelle de cette sauvegarde ;
- pour **chaque** pièce (ou un échantillon, ``--echantillon``), si son
  fichier s'ouvre dans le stockage et si son empreinte SHA-256 est celle
  de la fiche : une pièce dont le fichier manque ou diffère est nommée.

Le code de sortie est 1 dès qu'une pièce manque ou diffère : un compte
rendu de restauration qui dit « réussi » doit avoir eu 0.

Elle refuse de tourner si le courrier n'est pas en console
(``EMAIL_BACKEND_CONSOLE=1``) : une restauration de test qui enverrait
les alertes du jour aux vrais destinataires serait une restauration
ratée d'une autre façon. ``--sans-garde`` lève ce refus, en connaissance
de cause.
"""

import hashlib
import random

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count

from accounts.models import UserProfile
from core.models import ChangeLog, Country
from expenses.models import AuditLog, Dossier, Expense, Proof

CONSOLE = "django.core.mail.backends.console.EmailBackend"


def empreinte(fichier):
    h = hashlib.sha256()
    for bloc in iter(lambda: fichier.read(1024 * 1024), b""):
        h.update(bloc)
    return h.hexdigest()


class Command(BaseCommand):
    help = "Vérifie une base restaurée : décomptes, dernière trace, pièces ouvertes et comparées."

    def add_arguments(self, parser):
        parser.add_argument(
            "--echantillon", type=int, default=0,
            help="Ne vérifier qu'un échantillon aléatoire de N pièces (toutes par défaut).",
        )
        parser.add_argument(
            "--sans-garde", action="store_true",
            help="Tourner même si le courrier n'est pas en console.",
        )

    def handle(self, *args, **options):
        if settings.EMAIL_BACKEND != CONSOLE and not options["sans_garde"]:
            raise CommandError(
                "Le courrier n'est pas en console (EMAIL_BACKEND_CONSOLE=1) : cet "
                "environnement enverrait de vrais e-mails. Refus. (--sans-garde pour passer outre.)"
            )
        base = connection.settings_dict.get("NAME")
        self.stdout.write(f"Base : {base} · Stockage : {settings.STORAGES['default']['BACKEND']} "
                          f"{getattr(settings, 'AWS_S3_ENDPOINT_URL', '') or ''}")

        self.stdout.write("Comptes :")
        self.stdout.write(f"  actifs : {User.objects.filter(is_active=True).count()}")
        for role, nombre in (
            UserProfile.objects.values_list("role").annotate(n=Count("id")).order_by("role")
        ):
            self.stdout.write(f"  {role:<12} {nombre}")
        self.stdout.write(f"Pays : {Country.objects.count()} ({Country.objects.filter(is_active=True).count()} actifs)")
        self._par_statut("Dossiers", Dossier)
        self._par_statut("Lignes", Expense)
        self.stdout.write(f"Journal d'audit : {AuditLog.objects.count()} entrée(s)")
        derniere = AuditLog.objects.order_by("-created_at").values_list("created_at", flat=True).first()
        self.stdout.write(f"  dernière entrée : {derniere.isoformat(timespec='seconds') if derniere else 'aucune'}"
                          "  ← perte de données réelle de cette sauvegarde")
        self.stdout.write(f"Historique : {ChangeLog.objects.count()} entrée(s)")

        pieces = list(Proof.objects.select_related("dossier").order_by("pk"))
        if options["echantillon"] and options["echantillon"] < len(pieces):
            pieces = random.sample(pieces, options["echantillon"])
        self.stdout.write(f"Pièces : {Proof.objects.count()} fiche(s), {len(pieces)} vérifiée(s)")
        manquantes, differentes, ouvertes = [], [], 0
        for piece in pieces:
            try:
                with default_storage.open(piece.file.name, "rb") as fichier:
                    calculee = empreinte(fichier)
            except Exception as exc:  # fichier absent, stockage muet
                manquantes.append((piece, str(exc)[:120]))
                continue
            ouvertes += 1
            if calculee != piece.sha256:
                differentes.append(piece)
        for piece, erreur in manquantes:
            self.stdout.write(self.style.ERROR(
                f"  ✘ manquante : pièce {piece.pk} ({piece.file.name}) — {erreur}"
            ))
        for piece in differentes:
            self.stdout.write(self.style.ERROR(
                f"  ✘ empreinte différente : pièce {piece.pk} ({piece.file.name})"
            ))
        self.stdout.write(f"  ouvertes : {ouvertes} · manquantes : {len(manquantes)} · différentes : {len(differentes)}")

        if manquantes or differentes:
            self.stdout.write(self.style.ERROR("✘ Restauration incomplète : voir les pièces ci-dessus."))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("✔ Base et pièces cohérentes."))

    def _par_statut(self, libelle, modele):
        total = modele.objects.count()
        detail = ", ".join(
            f"{statut} {n}"
            for statut, n in modele.objects.values_list("status").annotate(n=Count("id")).order_by("status")
        )
        self.stdout.write(f"{libelle} : {total} ({detail or 'aucun'})")
