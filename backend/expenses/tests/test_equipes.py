"""Cloisonnement par équipe : un manager ne voit que les siennes.

Le cloisonnement par pays ne suffit pas : deux équipes d'un même pays ne
doivent pas lire les dépenses l'une de l'autre. ``CountryScopedMixin`` filtre
sur ``team_lookup`` quand le profil d'un manager porte des équipes ; un
manager sans équipe garde tout son pays.

Le mécanisme lui-même est livré par ``accounts`` : ces tests sont ignorés
tant que le mixin ne déclare pas ``team_lookup``, et s'exécutent dès qu'il
le fait.
"""

import unittest
from datetime import date

from django.utils import timezone
from rest_framework import status

from accounts.models import Role
from accounts.scoping import CountryScopedMixin
from accounts.tests.test_scoping import make_user
from core.models import Team
from expenses.models import Dossier, Proof

from .base import ExpenseTestCase

LIVRE = hasattr(CountryScopedMixin, "team_lookup")


@unittest.skipUnless(LIVRE, "CountryScopedMixin.team_lookup pas encore livré")
class CloisonnementParEquipeTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.equipe_a = self.team
        self.equipe_b = Team.objects.create(country=self.togo, name="Équipe Kara")
        self.dossier_a = self.dossier
        self.dossier_b = Dossier.objects.create(
            number="N-0002", label="Mission Kara", country=self.togo,
            team=self.equipe_b, owner=self.manager, date=date(self.year, 3, 16),
            created_by="quelqu-un-de-kara",
        )
        self.ligne_a = self.make_expense(title="Carburant Lomé")
        self.ligne_b = self.make_expense(
            title="Carburant Kara", dossier=self.dossier_b, team=self.equipe_b,
            created_by="quelqu-un-de-kara",
        )
        self.piece_a = self._piece(self.dossier_a, "a")
        self.piece_b = self._piece(self.dossier_b, "b")

        self.manager_a = make_user("manager.lome", Role.MANAGER, [self.togo])
        self.manager_a.profile.teams.set([self.equipe_a])
        self.manager_sans_equipe = make_user("manager.togo", Role.MANAGER, [self.togo])

    def _piece(self, dossier, empreinte):
        return Proof.objects.create(
            dossier=dossier, file="justificatifs/f.pdf",
            original_name="facture.pdf", sha256=empreinte * 64,
        )

    def _payload(self, **extra):
        data = {
            "dossier": self.dossier_a.pk, "country": self.togo.pk,
            "date": timezone.now().isoformat(), "title": "Dépense",
            "amount": "1000.00", "team": self.equipe_a.pk, "owner": self.manager.pk,
        }
        data.update(extra)
        return data

    def test_un_manager_ne_liste_que_les_dossiers_de_ses_equipes(self):
        self.login(self.manager_a)

        dossiers = self.client.get("/api/dossiers/")
        lignes = self.client.get("/api/expenses/")
        registre = self.client.get("/api/expenses/register/")
        pieces = self.client.get("/api/proofs/")

        self.assertEqual([d["id"] for d in dossiers.data["results"]], [self.dossier_a.pk])
        self.assertEqual([e["id"] for e in lignes.data["results"]], [self.ligne_a.pk])
        self.assertEqual([e["id"] for e in registre.data["results"]], [self.ligne_a.pk])
        self.assertEqual([p["id"] for p in pieces.data["results"]], [self.piece_a.pk])

    def test_l_equipe_voisine_n_existe_pas_pour_lui(self):
        """Comme pour le pays : hors périmètre, l'objet répond 404, sans
        révéler son existence."""
        self.login(self.manager_a)

        dossier = self.client.get(f"/api/dossiers/{self.dossier_b.pk}/")
        ligne = self.client.get(f"/api/expenses/{self.ligne_b.pk}/")
        piece = self.client.get(f"/api/proofs/{self.piece_b.pk}/")

        self.assertEqual(dossier.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(ligne.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(piece.status_code, status.HTTP_404_NOT_FOUND)

    def test_il_ne_modifie_pas_l_equipe_voisine(self):
        self.login(self.manager_a)

        dossier = self.client.patch(
            f"/api/dossiers/{self.dossier_b.pk}/", {"label": "Piraté"}
        )
        ligne = self.client.patch(
            f"/api/expenses/{self.ligne_b.pk}/", {"amount": "1.00"}
        )

        self.assertEqual(dossier.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(ligne.status_code, status.HTTP_404_NOT_FOUND)
        self.ligne_b.refresh_from_db()
        self.assertEqual(str(self.ligne_b.amount), "100000.00")

    def test_il_ne_cree_que_dans_ses_equipes(self):
        """La charge utile est revalidée : déclarer une équipe voisine — ou
        un dossier voisin — est refusé, sans rien apprendre au demandeur."""
        self.login(self.manager_a)

        chez_lui = self.client.post("/api/expenses/", self._payload())
        equipe_voisine = self.client.post(
            "/api/expenses/", self._payload(team=self.equipe_b.pk)
        )
        dossier_voisin = self.client.post(
            "/api/expenses/", self._payload(dossier=self.dossier_b.pk)
        )

        self.assertEqual(chez_lui.status_code, status.HTTP_201_CREATED, chez_lui.data)
        self.assertIn(
            equipe_voisine.status_code,
            (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN),
        )
        self.assertIn(
            dossier_voisin.status_code,
            (status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN),
        )
        self.assertEqual(self.dossier_b.expenses.count(), 1)
        self.assertFalse(self.dossier_a.expenses.filter(team=self.equipe_b).exists())

    def test_le_detail_d_un_dossier_ne_montre_que_les_lignes_de_ses_equipes(self):
        """Le détail applique le même filtre que la liste : une ligne d'une
        autre équipe, ou sans équipe, glissée dans le dossier (import,
        données anciennes) n'apparaît pas au manager cloisonné."""
        self.make_expense(title="Glissée de Kara", team=self.equipe_b)
        self.make_expense(title="Sans équipe", team=None)
        self.login(self.manager_a)

        detail = self.client.get(f"/api/dossiers/{self.dossier_a.pk}/")
        liste = self.client.get(f"/api/expenses/?dossier={self.dossier_a.pk}")

        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual([e["id"] for e in detail.data["expenses"]], [self.ligne_a.pk])
        # Même primitive de périmètre des deux côtés : les deux réponses
        # portent exactement les mêmes lignes.
        self.assertEqual(
            [e["id"] for e in detail.data["expenses"]],
            [e["id"] for e in liste.data["results"]],
        )

    def test_un_manager_cloisonne_declare_dans_une_de_ses_equipes(self):
        """Sans équipe, il créerait quelque chose qu'il ne peut plus relire :
        le dossier et la ligne exigent une de ses équipes."""
        self.login(self.manager_a)
        dossier_payload = {
            "number": "N-0100", "label": "Salon", "country": self.togo.pk,
            "date": f"{self.year}-04-01",
        }

        dossier_sans = self.client.post("/api/dossiers/", dossier_payload)
        ligne_sans = self.client.post("/api/expenses/", self._payload(team=None), format="json")
        dossier_avec = self.client.post(
            "/api/dossiers/", {**dossier_payload, "team": self.equipe_a.pk}
        )
        ligne_avec = self.client.post("/api/expenses/", self._payload())

        self.assertEqual(dossier_sans.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Choisissez", str(dossier_sans.data["team"]))
        self.assertEqual(ligne_sans.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Choisissez", str(ligne_sans.data["team"]))
        self.assertEqual(dossier_avec.status_code, status.HTTP_201_CREATED, dossier_avec.data)
        self.assertEqual(ligne_avec.status_code, status.HTTP_201_CREATED, ligne_avec.data)
        relu_dossier = self.client.get(f"/api/dossiers/{dossier_avec.data['id']}/")
        relue_ligne = self.client.get(f"/api/expenses/{ligne_avec.data['id']}/")
        self.assertEqual(relu_dossier.status_code, status.HTTP_200_OK)
        self.assertEqual(relue_ligne.status_code, status.HTTP_200_OK)

    def test_un_manager_sans_equipe_voit_tout_son_pays(self):
        self.login(self.manager_sans_equipe)

        dossiers = self.client.get("/api/dossiers/")
        lignes = self.client.get("/api/expenses/")

        self.assertEqual(dossiers.data["count"], 2)
        self.assertEqual(lignes.data["count"], 2)

    def test_le_dm_n_est_pas_cloisonne_par_equipe(self):
        """Le DM contrôle pour le siège, fût-il restreint au Togo : les
        équipes de son profil, s'il en a, ne le restreignent pas."""
        dm = make_user("dm.togo", Role.DM, [self.togo])
        dm.profile.teams.set([self.equipe_a])
        self.login(dm)

        response = self.client.get("/api/dossiers/")

        self.assertEqual(response.data["count"], 2)
