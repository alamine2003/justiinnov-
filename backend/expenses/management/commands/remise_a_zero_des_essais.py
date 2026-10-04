"""Retire, une seule fois, les saisies d'essai d'avant l'ouverture (décision 113).

La plateforme ne supprime rien hors brouillon : une dépense déclarée est
irréversible. Avant l'ouverture aux filiales, la production ne porte
pourtant que des essais — des dossiers, des lignes et des pièces saisis
pour éprouver l'outil, dont certains clôturés. La direction a décidé de
les retirer avant que les vraies déclarations n'arrivent ; cette commande
est la seule porte pour le faire, et elle ne s'ouvre qu'une fois.

Ce qu'elle retire : chaque dossier, ses lignes, leurs demandes de
rectification et ses pièces (fiches et fichiers, ceux-ci effacés après le
commit, comme au retrait d'un brouillon). Ce qu'elle garde : comptes,
pays, équipes, projets, enveloppes, référentiel — et les journaux, qui ne
se purgent jamais : chaque objet retiré y laisse une entrée ``purged``
avec ce qu'il portait, le motif et le nom de la sauvegarde qui le garde.

Sans ``--executer``, elle ne fait que dire ce qu'elle retirerait. Avec,
elle exige le nom de la base, comme ``deploy/restaurer.sh``.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Count, Sum

from accounts.permissions import exiger_la_capacite, get_access
from core.journal import Trace
from core.regles import PermissionRefusee

from ... import stockage
from ...audit import enregistrer, preparer
from ...models import AuditLog, Dossier, Expense, Proof, Rectification

PURGED = AuditLog.Action.PURGED


class Command(BaseCommand):
    help = "Retire une fois les dossiers, lignes et pièces d'essai (décision 113)."

    def add_arguments(self, parser):
        parser.add_argument("--compte", required=True,
                            help="Administrateur au nom duquel la remise à zéro est tracée.")
        parser.add_argument("--motif", required=True, help="Pourquoi : écrit dans chaque entrée.")
        parser.add_argument("--sauvegarde", required=True,
                            help="Nom du dump pris juste avant, qui garde ce qui part.")
        parser.add_argument("--executer", action="store_true",
                            help="Retirer pour de bon ; sans elle, la commande ne fait que compter.")
        parser.add_argument("--base", default="",
                            help="Nom de la base, à recopier : exigé avec --executer.")

    def handle(self, *args, **options):
        motif = options["motif"].strip()
        sauvegarde = options["sauvegarde"].strip()
        if not motif or not sauvegarde:
            raise CommandError("Le motif et le nom de la sauvegarde sont obligatoires.")
        acteur = User.objects.filter(username=options["compte"], is_active=True).first()
        if acteur is None:
            raise CommandError(f"Aucun compte actif « {options['compte']} ».")
        try:
            exiger_la_capacite("configuration.manage", get_access(acteur))
        except PermissionRefusee as exc:
            raise CommandError(f"« {acteur.username} » n'administre pas la plateforme.") from exc
        deja = AuditLog.objects.filter(action=PURGED).order_by("created_at").first()
        if deja is not None:
            raise CommandError(
                f"La remise à zéro a déjà eu lieu le {deja.created_at:%Y-%m-%d %H:%M} "
                f"par « {deja.user} » : elle ne se fait qu'une fois."
            )

        self._compter()
        if not options["executer"]:
            self.stdout.write("Rien n'est retiré : relancez avec --executer --base <nom>.")
            return
        base = connection.settings_dict.get("NAME")
        if options["base"] != base:
            raise CommandError(f"--base doit recopier le nom de la base visée : « {base} ».")

        trace = Trace.depuis_compte(acteur)
        with transaction.atomic():
            retires = self._retirer(trace, motif=motif, sauvegarde=sauvegarde)
        self.stdout.write(self.style.SUCCESS(
            f"✔ Remise à zéro faite : {retires['dossiers']} dossier(s), "
            f"{retires['lignes']} ligne(s), {retires['pieces']} pièce(s), "
            f"{retires['rectifications']} demande(s) de rectification retirés, "
            "chacun tracé au journal d'audit."
        ))

    def _compter(self):
        self.stdout.write(f"Base : {connection.settings_dict.get('NAME')}")
        par_pays = (
            Dossier.objects.values("country__name")
            .annotate(n=Count("id")).order_by("country__name")
        )
        for ligne in par_pays:
            self.stdout.write(f"  {ligne['country__name']} : {ligne['n']} dossier(s)")
        lignes = Expense.objects.values("status").annotate(n=Count("id"), total=Sum("amount"))
        for ligne in lignes.order_by("status"):
            self.stdout.write(f"  lignes {ligne['status']} : {ligne['n']} ({ligne['total']})")
        self.stdout.write(
            f"À retirer : {Dossier.objects.count()} dossier(s), {Expense.objects.count()} "
            f"ligne(s), {Proof.objects.count()} pièce(s), "
            f"{Rectification.objects.count()} demande(s) de rectification."
        )

    def _retirer(self, trace, *, motif, sauvegarde):
        commun = {"motif": motif, "sauvegarde": sauvegarde}
        entrees = []
        retires = dict.fromkeys(("dossiers", "lignes", "pieces", "rectifications"), 0)
        dossiers = (
            Dossier.objects.select_for_update(of=("self",))
            .select_related("country").order_by("pk")
        )
        for dossier in dossiers:
            lignes = list(dossier.expenses.select_for_update(of=("self",)).order_by("pk"))
            for demande in Rectification.objects.filter(expense__dossier=dossier).order_by("pk"):
                entrees.append(preparer(
                    trace, PURGED, demande, label=f"Remise à zéro — {demande}",
                    country=dossier.country, status=demande.status,
                    expense_id=demande.expense_id, dossier_id=dossier.pk, **commun,
                ))
                demande.delete()
                retires["rectifications"] += 1
            # La plus récente d'abord : une version protège celle qu'elle remplace.
            for piece in dossier.proofs.select_for_update(of=("self",)).order_by("-pk"):
                entrees.append(preparer(
                    trace, PURGED, piece, label=f"Remise à zéro — {piece}",
                    country=dossier.country, sha256=piece.sha256, file=piece.file.name,
                    status=piece.status, expense_id=piece.expense_id,
                    dossier=dossier.number, dossier_id=dossier.pk, **commun,
                ))
                stockage.programmer_la_suppression(piece, trace=trace, dossier=dossier)
                piece.delete()
                retires["pieces"] += 1
            for ligne in lignes:
                entrees.append(preparer(
                    trace, PURGED, ligne, label=f"Remise à zéro — {ligne}",
                    amount=str(ligne.amount), justified_amount=str(ligne.justified_amount),
                    status=ligne.status, budget_id=ligne.budget_id,
                    dossier=dossier.number, dossier_id=dossier.pk, **commun,
                ))
                ligne.delete()
                retires["lignes"] += 1
            entrees.append(preparer(
                trace, PURGED, dossier, label=f"Remise à zéro — {dossier}",
                number=dossier.number, status=dossier.status,
                project_id=dossier.project_id, lines=len(lignes), **commun,
            ))
            dossier.delete()
            retires["dossiers"] += 1
        enregistrer(entrees)
        return retires
