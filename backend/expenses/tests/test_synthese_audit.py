"""L'audit en tableau de bord, et ses filtres (décision 111).

La synthèse compte en base ce que le super administrateur doit voir d'un
coup d'œil ; l'interface affiche. Elle lit les mêmes journaux que la page
Audit, cloisonnés de la même façon, et reste fermée au pays.
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework import status

from core.models import ChangeLog

from .base import ExpenseTestCase


class SyntheseTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.make_expense()
        self.submit_dossier()
        self.login(self.controller)
        rouvert = self.client.post(
            f"/api/dossiers/{self.dossier.pk}/reopen/", {"note": "Montant de la salle à revoir."}
        )
        self.assertEqual(rouvert.status_code, status.HTTP_200_OK, rouvert.data)
        droits = self.client.patch(
            "/api/permissions/",
            {"capabilities": {"rectifications.request": ["super_admin"]}},
            format="json",
        )
        self.assertEqual(droits.status_code, status.HTTP_200_OK, droits.data)

    def synthese(self, user=None, **params):
        self.login(user or self.doo)
        return self.client.get("/api/audit/synthese/", params)

    def test_le_pays_n_y_a_pas_acces(self):
        self.assertEqual(self.synthese(self.owner).status_code, status.HTTP_403_FORBIDDEN)

    def test_les_compteurs_disent_ce_qui_s_est_passe(self):
        reponse = self.synthese()

        self.assertEqual(reponse.status_code, status.HTTP_200_OK, reponse.data)
        compteurs = reponse.data["compteurs"]
        self.assertEqual(compteurs["declarations"], 1)
        self.assertEqual(compteurs["reouvertures"], 1)
        self.assertEqual(compteurs["changements_de_droits"], 1)
        self.assertEqual(compteurs["decisions"], 0)
        self.assertEqual(reponse.data["fin"], timezone.localdate().isoformat())
        self.assertEqual(reponse.data["debut"], (timezone.localdate() - timedelta(days=29)).isoformat())
        utilisateurs = {u["user"] for u in reponse.data["par_utilisateur"]}
        self.assertLessEqual({self.owner.username, self.controller.username}, utilisateurs)
        self.assertEqual([p["name"] for p in reponse.data["par_pays"]], ["Togo"])
        self.assertEqual(sum(j["circuit"] for j in reponse.data["par_jour"]), compteurs["circuit"])

    def test_a_surveiller_montre_la_reouverture_et_le_changement_de_droits(self):
        reponse = self.synthese()

        sources = {(e["source"], e["action"]) for e in reponse.data["a_surveiller"]}
        self.assertIn(("circuit", "reopened"), sources)
        self.assertIn(("referentiel", "updated"), sources)
        dates = [e["created_at"] for e in reponse.data["a_surveiller"]]
        self.assertEqual(dates, sorted(dates, reverse=True))

    def test_la_periode_et_le_pays_bornent_la_synthese(self):
        hier = timezone.localdate() - timedelta(days=1)
        passe = self.synthese(debut=hier - timedelta(days=10), fin=hier)
        voisin = self.synthese(country=self.ivoire.pk)

        self.assertEqual(passe.data["compteurs"]["circuit"], 0)
        self.assertEqual(passe.data["compteurs"]["referentiel"], 0)
        self.assertEqual(voisin.data["compteurs"]["declarations"], 0)
        self.assertEqual(voisin.data["par_pays"], [])

    def test_une_periode_a_l_envers_est_refusee(self):
        aujourd_hui = timezone.localdate()

        reponse = self.synthese(debut=aujourd_hui, fin=aujourd_hui - timedelta(days=1))

        self.assertEqual(reponse.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("debut", reponse.data)


class FiltresDuJournalTests(ExpenseTestCase):
    def setUp(self):
        super().setUp()
        self.make_expense()
        self.submit_dossier()
        self.login(self.controller)

    def test_le_journal_se_filtre_par_projet(self):
        du_projet = self.client.get("/api/audit/", {"projet": self.projet.pk})
        du_voisin = self.client.get("/api/audit/", {"projet": self.projet_ivoire.pk})

        self.assertEqual(du_projet.status_code, status.HTTP_200_OK)
        self.assertTrue(du_projet.data["results"])
        self.assertTrue(all(
            e["object_type"] in {"Dossier", "Expense"} for e in du_projet.data["results"]
        ))
        self.assertEqual(du_voisin.data["count"], 0)

    def test_le_journal_se_filtre_par_periode(self):
        demain = timezone.localdate() + timedelta(days=1)

        apres = self.client.get("/api/audit/", {"debut": demain.isoformat()})
        avant = self.client.get("/api/audit/", {"fin": demain.isoformat()})

        self.assertEqual(apres.data["count"], 0)
        self.assertGreater(avant.data["count"], 0)

    def test_l_historique_se_cherche_par_motif(self):
        self.login(self.owner)
        self.client.post(
            f"/api/projects/{self.projet.pk}/rename/",
            {"name": "Congrès de Lomé 2026", "motif": "Coquille sur l'année"}, format="json",
        )
        self.login(self.controller)

        trouve = self.client.get("/api/history/", {"search": "Coquille"})

        self.assertEqual(trouve.status_code, status.HTTP_200_OK)
        self.assertEqual([e["motif"] for e in trouve.data["results"]], ["Coquille sur l'année"])
        self.assertEqual(trouve.data["results"][0]["model_name"], ChangeLog.Models.PROJECT)
