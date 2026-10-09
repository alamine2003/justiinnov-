"""La corbeille du super administrateur (décision 120).

Tant que la configuration la tient ouverte, le super administrateur retire
un projet, un dossier, une ligne ou un justificatif, avec ce qui en
dépend : l'objet quitte sa table — enveloppes et numérotation se
recalculent —, la corbeille en garde une copie que la base refuse de
modifier ou de supprimer, et le stockage garde le fichier. Fermée, rien ne
part ; la RH lit la corbeille, ne la remplit pas et ne l'ouvre pas ; le
pays n'y a pas accès.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import DatabaseError, connection, transaction
from django.test.utils import CaptureQueriesContext
from rest_framework import status

from accounts.permissions import get_access
from budget.aggregates import consumption
from budget.models import Budget
from core import types_de_projets
from core.models import ChangeLog, Project, WorkflowConfiguration
from core.numerotation import creer_projet
from core.statuts import Status
from expenses.models import (
    AuditLog,
    Dossier,
    ElementSupprime,
    Expense,
    Proof,
    Rectification,
)
from expenses.stockage import pieces_orphelines
from notifications.models import Notification

from .base import ExpenseTestCase, in_memory_storage

MOTIF = "Saisie d'essai avant l'ouverture"
TRASHED = AuditLog.Action.TRASHED


def ouvrir_la_corbeille(ouverte=True):
    configuration, _ = WorkflowConfiguration.objects.get_or_create(pk=1)
    configuration.suppressions_ouvertes = ouverte
    configuration.save()


@in_memory_storage
class CorbeilleTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        ouvrir_la_corbeille()

    def jeter(self, nature, pk, user=None, motif=MOTIF):
        self.login(user or self.doo)
        return self.client.post(
            "/api/corbeille/", {"nature": nature, "id": pk, "motif": motif}, format="json"
        )

    def piece(self, ligne, contenu=b"%PDF-1.4 recu", **en_plus):
        return Proof.objects.create(
            dossier=ligne.dossier, expense=ligne,
            file=ContentFile(contenu, name="recu.pdf"), original_name="recu.pdf",
            sha256=en_plus.pop("sha256", "a" * 64), size=len(contenu),
            content_type="application/pdf", uploaded_by="owner.togo", **en_plus,
        )

    def ligne_cloturee(self, montant="40000.00"):
        ligne = self.make_expense(amount=montant, status=Status.CLOSED)
        Expense.objects.filter(pk=ligne.pk).update(justified_amount=Decimal(montant))
        ligne.refresh_from_db()
        return ligne

    # -- Ce qui part, et ce qui reste --------------------------------------

    def test_une_ligne_constatee_part_avec_ses_pieces_et_ses_rectifications(self):
        ligne = self.ligne_cloturee()
        piece = self.piece(ligne)
        Rectification.objects.create(
            expense=ligne, motif="Montant à revoir", requested_by="owner.togo",
            previous_status=Status.CLOSED, previous_justified_amount=ligne.amount,
        )

        reponse = self.jeter("ligne", ligne.pk)

        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        self.assertEqual(reponse.data["emportes"]["ligne"], 1)
        self.assertEqual(reponse.data["emportes"]["piece"], 1)
        self.assertFalse(Expense.objects.filter(pk=ligne.pk).exists())
        self.assertFalse(Proof.objects.filter(pk=piece.pk).exists())
        self.assertFalse(Rectification.objects.exists())
        tete = ElementSupprime.objects.get(racine__isnull=True)
        self.assertEqual(tete.nature, "ligne")
        self.assertEqual(tete.objet_id, ligne.pk)
        self.assertEqual(tete.montant, Decimal("40000.00"))
        self.assertEqual(tete.devise, "XOF")
        self.assertEqual(tete.motif, MOTIF)
        self.assertEqual(tete.supprime_par, self.doo.username)
        self.assertEqual(tete.donnees["status"], Status.CLOSED)
        self.assertEqual(len(tete.donnees["rectifications"]), 1)
        copie_piece = ElementSupprime.objects.get(nature="piece")
        self.assertEqual(copie_piece.racine, tete)
        self.assertEqual(copie_piece.fichier, piece.file.name)
        # Chaque objet laisse sa trace : la ligne, la pièce, la demande.
        self.assertEqual(
            sorted(AuditLog.objects.filter(action=TRASHED).values_list("object_type", flat=True)),
            ["Expense", "Proof", "Rectification"],
        )
        # Le stockage garde le fichier : la corbeille le cite.
        self.assertTrue(default_storage.exists(piece.file.name))

    def test_l_enveloppe_se_recalcule(self):
        ligne = self.ligne_cloturee("250000.00")
        self.assertEqual(consumption(ligne.budget)["consumed"], Decimal("250000.00"))

        self.jeter("ligne", ligne.pk)

        self.assertEqual(consumption(Budget.objects.get(pk=self.budget.pk))["consumed"], 0)

    def test_un_projet_emporte_tout_et_la_numerotation_repart(self):
        ligne = self.make_expense()
        self.piece(ligne)
        reference = self.projet.reference

        reponse = self.jeter("projet", self.projet.pk)

        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        self.assertEqual(
            reponse.data["emportes"], {"projet": 1, "dossier": 1, "ligne": 1, "piece": 1}
        )
        self.assertFalse(Project.objects.filter(pk=self.projet.pk).exists())
        self.assertFalse(Dossier.objects.filter(pk=self.dossier.pk).exists())
        self.assertEqual(reponse.data["element"]["emportes"], 3)
        # Le pays vidé recommence à -001.
        nouveau = creer_projet(Project(
            country=self.togo, name="Congrès de Kara", kind_id=types_de_projets.CONGRES,
        ))
        self.assertEqual(nouveau.reference, reference)
        # L'historique du référentiel a aussi tracé la suppression du projet.
        self.assertTrue(
            ChangeLog.objects.filter(
                model_name=ChangeLog.Models.PROJECT, action=ChangeLog.Actions.DELETED,
                object_id=self.projet.pk,
            ).exists()
        )

    def test_un_dossier_predefini_retire_se_recree_en_completant_le_projet(self):
        self.jeter("dossier", self.dossier.pk)
        self.assertFalse(Dossier.objects.filter(project=self.projet).exists())

        self.login(self.controller)
        reponse = self.client.post(f"/api/projects/{self.projet.pk}/completer/")

        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        self.assertTrue(
            Dossier.objects.filter(project=self.projet, kind=self.stands, predefini=True).exists()
        )

    def test_une_piece_part_avec_toutes_ses_versions(self):
        ligne = self.make_expense()
        premiere = self.piece(ligne)
        seconde = self.piece(ligne, b"%PDF-1.4 v2", replaces=premiere, version=2, sha256="b" * 64)

        reponse = self.jeter("piece", premiere.pk)

        self.assertEqual(reponse.status_code, status.HTTP_201_CREATED, reponse.data)
        self.assertEqual(reponse.data["emportes"]["piece"], 2)
        self.assertFalse(Proof.objects.filter(pk__in=[premiere.pk, seconde.pk]).exists())
        self.assertTrue(Expense.objects.filter(pk=ligne.pk).exists())

    def test_la_piece_d_une_ligne_constatee_ne_part_pas_seule(self):
        piece = self.piece(self.ligne_cloturee())

        reponse = self.jeter("piece", piece.pk)

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Proof.objects.filter(pk=piece.pk).exists())
        self.assertFalse(ElementSupprime.objects.exists())

    def test_le_projet_historique_et_le_projet_a_enveloppe_restent(self):
        historique = Project.objects.create(
            country=self.togo, name="Historique (avant 2.0)", is_historical=True,
        )
        Budget.objects.create(
            country=self.togo, year=self.year, amount=Decimal("1000.00"), project=self.projet,
        )

        for projet in (historique, self.projet):
            with self.subTest(projet=projet.name):
                reponse = self.jeter("projet", projet.pk)
                self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertTrue(Project.objects.filter(pk=projet.pk).exists())

    def test_un_projet_cite_par_une_ligne_d_un_autre_dossier_reste(self):
        """Depuis la 2.0, une ligne du dossier « Historique » peut encore
        citer son projet d'origine : elle le protège en base. Le refus le
        dit, au lieu d'un « réessayez » qui échouerait toujours."""
        historique = Project.objects.create(
            country=self.togo, name="Historique (avant 2.0)", is_historical=True,
        )
        ancien = Dossier.objects.create(
            number="ANCIEN-1", label="Ancien", country=self.togo, project=historique,
            team=self.team, owner=self.manager, date=self.dossier.date,
            created_by=self.owner.username,
        )
        self.make_expense(dossier=ancien, project=self.projet)

        reponse = self.jeter("projet", self.projet.pk)

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ANCIEN-1", str(reponse.data))
        self.assertTrue(Project.objects.filter(pk=self.projet.pk).exists())
        self.assertFalse(ElementSupprime.objects.exists())

    def test_une_version_qui_prouve_un_constat_retient_toute_la_chaine(self):
        """Une pièce d'avant la 2.0, remplacée sur une ligne justifiée :
        retirer l'ancienne emporterait la nouvelle, et la ligne resterait
        constatée sans preuve."""
        ancienne = Proof.objects.create(
            dossier=self.dossier, file=ContentFile(b"%PDF-1.4 a", name="a.pdf"),
            original_name="a.pdf", sha256="c" * 64, uploaded_by="owner.togo",
        )
        self.piece(self.ligne_cloturee(), replaces=ancienne, version=2, sha256="d" * 64)

        reponse = self.jeter("piece", ancienne.pk)

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Proof.objects.count(), 2)

    def test_la_fiche_du_projet_garde_ce_qui_en_est_parti(self):
        """Décision 110 : l'historique du projet dit aussi ce qui a été mis à
        la corbeille — la mise à la corbeille elle-même, et ce qui l'a précédée."""
        ligne = self.make_expense()
        AuditLog.objects.create(
            user="owner.togo", action=AuditLog.Action.CREATED, object_type="Expense",
            object_id=ligne.pk, label="Saisie", country=self.togo,
        )
        self.jeter("ligne", ligne.pk)
        self.jeter("dossier", self.dossier.pk)
        self.login(self.controller)

        entrees = self.client.get(f"/api/projects/{self.projet.pk}/historique/").data["entrees"]
        journal = self.client.get("/api/audit/", {"projet": self.projet.pk}).data["results"]

        vues = {(e["objet"], e["object_id"], e["action"]) for e in entrees}
        self.assertIn(("Expense", ligne.pk, "created"), vues)
        self.assertIn(("Expense", ligne.pk, "trashed"), vues)
        self.assertIn(("Dossier", self.dossier.pk, "trashed"), vues)
        self.assertEqual(
            {(e["object_type"], e["action"]) for e in journal if e["action"] == "trashed"},
            {("Expense", "trashed"), ("Dossier", "trashed")},
        )

    # -- Chasse aux bugs de la 2.3.0 ------------------------------------------

    def test_une_piece_de_dossier_ne_part_pas_si_une_ligne_est_constatee(self):
        """Une pièce d'avant la 2.0 prouve toutes les lignes de son dossier :
        une seule ligne justifiée suffit à la retenir, même si le dossier,
        lui, est encore en contrôle."""
        Dossier.objects.filter(pk=self.dossier.pk).update(status=Status.IN_REVIEW)
        self.ligne_cloturee()
        piece = Proof.objects.create(
            dossier=self.dossier, file=ContentFile(b"%PDF-1.4 d", name="d.pdf"),
            original_name="d.pdf", sha256="e" * 64, uploaded_by="owner.togo",
        )
        self.login(self.doo)
        detail = self.client.get(f"/api/dossiers/{self.dossier.pk}/").data
        self.assertFalse(next(p for p in detail["proofs"] if p["id"] == piece.pk)["can_trash"])

        reponse = self.jeter("piece", piece.pk)

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Proof.objects.filter(pk=piece.pk).exists())

    def test_la_derniere_ligne_d_un_dossier_declare_ne_part_pas_seule(self):
        """Vidé, un dossier déclaré se clôturerait à vide et garderait pour
        toujours la place de son type dans le projet."""
        ligne = self.make_expense(status=Status.SUBMITTED)
        Dossier.objects.filter(pk=self.dossier.pk).update(status=Status.SUBMITTED)

        reponse = self.jeter("ligne", ligne.pk)

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(self.dossier.number, str(reponse.data))
        self.assertTrue(Expense.objects.filter(pk=ligne.pk).exists())
        # Avec une autre ligne, ou en brouillon, elle part.
        self.make_expense(status=Status.SUBMITTED, title="Repas")
        self.assertEqual(self.jeter("ligne", ligne.pk).status_code, status.HTTP_201_CREATED)

    def test_la_tete_est_la_version_choisie(self):
        ligne = self.make_expense()
        premiere = self.piece(ligne)
        self.piece(ligne, b"%PDF-1.4 v2", replaces=premiere, version=2, sha256="b" * 64)

        reponse = self.jeter("piece", premiere.pk)

        self.assertEqual(reponse.data["element"]["objet_id"], premiere.pk)

    def test_le_motif_va_a_l_historique_du_projet_retire(self):
        self.jeter("projet", self.projet.pk)

        entree = ChangeLog.objects.get(
            model_name=ChangeLog.Models.PROJECT, action=ChangeLog.Actions.DELETED,
            object_id=self.projet.pk,
        )
        self.assertEqual(entree.motif, MOTIF)

    def test_le_journal_du_projet_retire_montre_son_retrait(self):
        self.jeter("projet", self.projet.pk)
        self.login(self.controller)

        journal = self.client.get("/api/audit/", {"projet": self.projet.pk}).data["results"]

        self.assertIn(("Project", "trashed"), {(e["object_type"], e["action"]) for e in journal})

    def test_une_decision_de_rectification_verrouille_le_dossier_d_abord(self):
        """Même ordre que la corbeille — dossier, puis ligne et demandes —
        sinon les deux s'interbloquent."""
        from expenses.transitions import _verrouiller_la_demande

        ligne = self.ligne_cloturee()
        demande = Rectification.objects.create(
            expense=ligne, motif="Montant à revoir", requested_by="owner.togo",
            previous_status=Status.CLOSED, previous_justified_amount=ligne.amount,
        )
        rh = get_access(self.controller)
        with CaptureQueriesContext(connection) as requetes, transaction.atomic():
            _verrouiller_la_demande(demande, rh)
        verrous = [q["sql"] for q in requetes if "FOR UPDATE" in q["sql"]]
        # La cible du premier verrou, pas une simple jointure : l'ancien
        # verrou de la demande joignait déjà le dossier.
        self.assertIn('FROM "expenses_dossier"', verrous[0])
        self.assertNotIn("expenses_rectification", verrous[0])
        self.assertIn('FROM "expenses_rectification"', verrous[1])

    def test_un_objet_disparu_pendant_l_attente_du_verrou_repond_404(self):
        """Une requête qui attendait le verrou d'un objet mis à la corbeille
        entre-temps le trouve absent : 404, pas 500."""
        from unittest import mock

        from expenses import transitions

        ligne = self.make_expense()

        def retire_pendant_l_attente(*args, **kwargs):
            Expense.objects.filter(pk=ligne.pk).delete()

        self.login(self.owner)
        with mock.patch.object(transitions, "exiger_la_capacite", retire_pendant_l_attente):
            reponse = self.client.delete(f"/api/expenses/{ligne.pk}/")

        self.assertEqual(reponse.status_code, status.HTTP_404_NOT_FOUND)

    def test_un_objet_introuvable_ailleurs_reste_un_defaut(self):
        """Seules les relectures sous verrou se traduisent en 404 : ailleurs,
        un objet introuvable est un défaut, que le gestionnaire ne masque pas."""
        from core.exceptions import gestionnaire_d_exception

        self.assertIsNone(gestionnaire_d_exception(Dossier.DoesNotExist("parti"), {}))

    def test_une_version_posee_sur_une_ligne_suit_la_piece_de_dossier_qu_elle_remplace(self):
        """Chaîne mixte : v1 d'avant la 2.0, sans ligne, remplacée par v2 sur
        une ligne brouillon ; une autre ligne du dossier est clôturée. v1
        prouve encore le dossier : v2 ne part pas, et la fiche le dit."""
        v1 = Proof.objects.create(
            dossier=self.dossier, file=ContentFile(b"%PDF-1.4 a", name="a.pdf"),
            original_name="a.pdf", sha256="c" * 64, uploaded_by="owner.togo",
        )
        v2 = self.piece(self.make_expense(), replaces=v1, version=2, sha256="d" * 64)
        self.ligne_cloturee()
        self.login(self.doo)

        detail = self.client.get(f"/api/dossiers/{self.dossier.pk}/").data

        self.assertFalse(next(p for p in detail["proofs"] if p["id"] == v2.pk)["can_trash"])
        self.assertEqual(self.jeter("piece", v2.pk).status_code, status.HTTP_400_BAD_REQUEST)
        # Archivée, v1 ne prouve plus rien : la chaîne part.
        Proof.objects.filter(pk=v1.pk).update(status=Proof.ProofStatus.ARCHIVED)
        detail = self.client.get(f"/api/dossiers/{self.dossier.pk}/").data
        self.assertTrue(next(p for p in detail["proofs"] if p["id"] == v2.pk)["can_trash"])
        self.assertEqual(self.jeter("piece", v2.pk).status_code, status.HTTP_201_CREATED)

    def test_la_fiche_ne_fait_pas_une_requete_par_piece_de_dossier(self):
        def requetes_de_la_fiche():
            self.login(self.doo)
            with CaptureQueriesContext(connection) as requetes:
                self.client.get(f"/api/dossiers/{self.dossier.pk}/")
            return len(requetes)

        def piece_de_dossier(n):
            Proof.objects.create(
                dossier=self.dossier, file=ContentFile(b"%PDF-1.4 x", name=f"{n}.pdf"),
                original_name=f"{n}.pdf", sha256=f"{n:064d}", uploaded_by="owner.togo",
            )

        self.make_expense()
        piece_de_dossier(1)
        requetes_de_la_fiche()  # caches de configuration et de session chauds
        une = requetes_de_la_fiche()
        for n in range(2, 6):
            piece_de_dossier(n)

        self.assertEqual(requetes_de_la_fiche(), une)

    def test_un_objet_inconnu_n_existe_pas(self):
        self.assertEqual(self.jeter("ligne", 999999).status_code, status.HTTP_404_NOT_FOUND)

    def test_sans_motif_rien_ne_part(self):
        ligne = self.make_expense()

        reponse = self.jeter("ligne", ligne.pk, motif="  ")

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("motif", reponse.data)
        self.assertTrue(Expense.objects.filter(pk=ligne.pk).exists())

    def test_le_pays_est_prevenu(self):
        self.jeter("dossier", self.dossier.pk)

        notification = Notification.objects.get(kind=Notification.Kind.TRASHED)
        self.assertEqual(notification.recipient, self.owner)
        self.assertIn(MOTIF, str(notification.body))

    # -- La corbeille ne se vide pas ----------------------------------------

    def test_la_copie_ne_se_modifie_ni_ne_se_supprime(self):
        self.jeter("dossier", self.dossier.pk)
        element = ElementSupprime.objects.get()

        for operation in (
            lambda: ElementSupprime.objects.filter(pk=element.pk).update(motif="Autre"),
            lambda: ElementSupprime.objects.filter(pk=element.pk).delete(),
        ):
            with self.subTest(operation=operation), self.assertRaises(DatabaseError):
                with transaction.atomic():
                    operation()
        self.assertEqual(ElementSupprime.objects.get().motif, MOTIF)

    def test_l_api_ne_modifie_ni_ne_supprime(self):
        self.jeter("dossier", self.dossier.pk)
        element = ElementSupprime.objects.get()
        self.login(self.doo)

        for methode in ("put", "patch", "delete"):
            with self.subTest(methode=methode):
                reponse = getattr(self.client, methode)(f"/api/corbeille/{element.pk}/")
                self.assertEqual(reponse.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_le_fichier_se_telecharge_depuis_la_corbeille(self):
        ligne = self.make_expense()
        self.piece(ligne, b"%PDF-1.4 conserve")
        self.jeter("ligne", ligne.pk)
        copie = ElementSupprime.objects.get(nature="piece")
        self.login(self.controller)

        reponse = self.client.get(f"/api/corbeille/{copie.pk}/fichier/")

        self.assertEqual(reponse.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(reponse.streaming_content), b"%PDF-1.4 conserve")
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.DOWNLOADED, object_type="ElementSupprime",
                object_id=copie.pk,
            ).exists()
        )

    def test_un_fichier_garde_n_est_pas_un_orphelin(self):
        ligne = self.make_expense()
        piece = self.piece(ligne)
        self.jeter("ligne", ligne.pk)

        orphelins = [chemin for chemin, _ in pieces_orphelines(age_minimal=timedelta(0))]

        self.assertNotIn(piece.file.name, orphelins)

    def test_la_liste_montre_les_tetes_et_ce_qu_elles_ont_emporte(self):
        ligne = self.make_expense()
        self.piece(ligne)
        self.jeter("dossier", self.dossier.pk)
        self.login(self.controller)

        tetes = self.client.get("/api/corbeille/", {"tetes": "true"}).data["results"]
        tete = tetes[0]
        emportes = self.client.get("/api/corbeille/", {"racine": tete["id"]}).data["results"]

        self.assertEqual(len(tetes), 1)
        self.assertEqual(tete["nature"], "dossier")
        self.assertEqual(tete["emportes"], 2)
        self.assertEqual(sorted(e["nature"] for e in emportes), ["ligne", "piece"])
        piece = next(e for e in emportes if e["nature"] == "piece")
        self.assertEqual(piece["download_url"], f"/api/corbeille/{piece['id']}/fichier/")

    def test_la_liste_ne_coute_pas_une_requete_par_element(self):
        self.jeter("ligne", self.make_expense().pk)
        une = self._requetes_de_la_liste()
        for _ in range(3):
            self.jeter("ligne", self.make_expense().pk)

        self.assertEqual(self._requetes_de_la_liste(), une)

    def _requetes_de_la_liste(self):
        self.login(self.controller)
        with CaptureQueriesContext(connection) as requetes:
            self.assertEqual(self.client.get("/api/corbeille/").status_code, status.HTTP_200_OK)
        return len(requetes)

    # -- Qui peut quoi -------------------------------------------------------

    def test_fermee_rien_ne_part(self):
        ouvrir_la_corbeille(False)
        ligne = self.make_expense()

        reponse = self.jeter("ligne", ligne.pk)

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Expense.objects.filter(pk=ligne.pk).exists())

    def test_ni_la_rh_ni_le_pays_ne_mettent_a_la_corbeille(self):
        ligne = self.make_expense()

        for compte in (self.controller, self.owner):
            with self.subTest(compte=compte.username):
                reponse = self.jeter("ligne", ligne.pk, user=compte)
                self.assertEqual(reponse.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Expense.objects.filter(pk=ligne.pk).exists())

    def test_la_rh_lit_la_corbeille_le_pays_non(self):
        self.login(self.controller)
        self.assertEqual(self.client.get("/api/corbeille/").status_code, status.HTTP_200_OK)
        self.login(self.owner)
        self.assertEqual(self.client.get("/api/corbeille/").status_code, status.HTTP_403_FORBIDDEN)

    def test_seul_le_super_admin_ouvre_ou_ferme_la_corbeille(self):
        ouvrir_la_corbeille(False)
        self.login(self.controller)
        refus = self.client.patch(
            "/api/workflow-configuration/", {"suppressions_ouvertes": True}, format="json"
        )
        # La RH garde le reste de la configuration, l'interrupteur inchangé compris.
        accepte = self.client.patch(
            "/api/workflow-configuration/",
            {"suppressions_ouvertes": False, "warn_without_proof_submission": False},
            format="json",
        )
        self.login(self.doo)
        ouverture = self.client.patch(
            "/api/workflow-configuration/", {"suppressions_ouvertes": True}, format="json"
        )

        self.assertEqual(refus.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(accepte.status_code, status.HTTP_200_OK, accepte.data)
        self.assertEqual(ouverture.status_code, status.HTTP_200_OK, ouverture.data)
        self.assertTrue(WorkflowConfiguration.objects.get(pk=1).suppressions_ouvertes)
        trace = ChangeLog.objects.filter(
            model_name=ChangeLog.Models.WORKFLOW_CONFIGURATION, performed_by=self.doo.username
        ).latest("pk")
        self.assertIn("suppressions_ouvertes", trace.changed_fields)

    def test_la_corbeille_est_fermee_par_defaut(self):
        self.assertFalse(WorkflowConfiguration().suppressions_ouvertes)

    def test_me_dit_si_la_corbeille_est_ouverte(self):
        self.login(self.doo)
        self.assertTrue(self.client.get("/api/me/").data["workflow"]["suppressions_ouvertes"])

    def test_allowed_actions_proposent_la_corbeille_au_super_admin_seul(self):
        ligne = self.make_expense()
        self.piece(ligne)

        def actions(user):
            self.login(user)
            detail = self.client.get(f"/api/dossiers/{self.dossier.pk}/").data
            return (
                "trash" in detail["allowed_actions"],
                "trash" in detail["expenses"][0]["allowed_actions"],
                detail["proofs"][0]["can_trash"],
            )

        self.assertEqual(actions(self.doo), (True, True, True))
        self.assertEqual(actions(self.controller), (False, False, False))
        self.assertEqual(actions(self.owner), (False, False, False))
        ouvrir_la_corbeille(False)
        self.assertEqual(actions(self.doo), (False, False, False))
