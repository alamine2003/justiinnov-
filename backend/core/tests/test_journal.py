"""La façade ``core.journal.tracer`` : un journal par famille, une signature."""

from django.test import RequestFactory, TestCase

from accounts.tests.test_scoping import make_user
from core.journal import difference, enregistrer, preparer, tracer
from core.models import ChangeLog, Country
from expenses.models import AuditLog


class TracerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.togo = Country.objects.create(name="Togo", code="TG", currency="XOF")
        cls.user = make_user("siege", "super_admin", [])

    def _requete(self):
        requete = RequestFactory().post(
            "/api/", REMOTE_ADDR="10.20.30.40", HTTP_USER_AGENT="Navigateur de test"
        )
        requete.user = self.user
        return requete

    def test_une_famille_du_referentiel_ecrit_dans_l_historique(self):
        entree = tracer(
            self._requete(), ChangeLog.Actions.UPDATED, self.togo,
            famille="referentiel", entite=ChangeLog.Models.COUNTRY, country=self.togo,
            avant={"name": "Togo", "currency": "XOF"},
            apres={"name": "Togo", "currency": "GHS"},
        )
        self.assertIsInstance(entree, ChangeLog)
        self.assertEqual(entree.performed_by, "siege")
        self.assertEqual(entree.ip_address, "10.20.30.40")
        self.assertEqual(entree.changed_fields, ["currency"])
        self.assertEqual(entree.diff, {"currency": ["XOF", "GHS"]})
        self.assertEqual(entree.country, self.togo)

    def test_une_famille_du_circuit_ecrit_dans_l_audit(self):
        entree = tracer(
            self._requete(), AuditLog.Action.UPDATED, self.togo,
            famille="circuit", avant={"amount": "1"}, apres={"amount": "2"}, note="x",
        )
        self.assertIsInstance(entree, AuditLog)
        self.assertEqual(entree.user, "siege")
        self.assertEqual(entree.object_type, "Country")
        self.assertEqual(entree.object_id, self.togo.pk)
        self.assertEqual(entree.ip_address, "10.20.30.40")
        self.assertEqual(entree.user_agent, "Navigateur de test")
        self.assertEqual(
            entree.detail, {"note": "x", "before": {"amount": "1"}, "after": {"amount": "2"}}
        )

    def test_une_action_sans_objet_nomme_son_type(self):
        entree = tracer(
            self._requete(), AuditLog.Action.DOWNLOADED, "Export",
            famille="export", label="Export", country=self.togo.pk,
            detail={"country": self.togo.pk},
        )
        self.assertEqual(entree.object_type, "Export")
        self.assertIsNone(entree.object_id)
        self.assertEqual(entree.country, self.togo)
        self.assertEqual(entree.detail, {"country": self.togo.pk})

    def test_une_famille_inconnue_est_refusee(self):
        with self.assertRaises(ValueError):
            tracer(self._requete(), "x", self.togo, famille="inconnue")

    def test_le_referentiel_exige_une_entite(self):
        with self.assertRaises(ValueError):
            tracer(self._requete(), ChangeLog.Actions.UPDATED, self.togo, famille="referentiel")

    def test_hors_requete_l_auteur_reste_vide(self):
        entree = tracer(None, AuditLog.Action.CREATED, self.togo, famille="circuit")
        self.assertEqual(entree.user, "")
        self.assertIsNone(entree.ip_address)
        self.assertEqual(entree.user_agent, "")

    def test_enregistrer_ecrit_les_deux_journaux_par_lots(self):
        entrees = [
            preparer(self._requete(), AuditLog.Action.CREATED, self.togo, famille="circuit"),
            preparer(
                self._requete(), ChangeLog.Actions.CREATED, self.togo,
                famille="referentiel", entite=ChangeLog.Models.COUNTRY,
            ),
            preparer(self._requete(), AuditLog.Action.CREATED, self.togo, famille="piece"),
        ]
        avant_audit, avant_histo = AuditLog.objects.count(), ChangeLog.objects.count()
        ecrites = enregistrer(entrees)
        self.assertEqual(len(ecrites), 3)
        self.assertEqual(AuditLog.objects.count(), avant_audit + 2)
        self.assertEqual(ChangeLog.objects.count(), avant_histo + 1)

    def test_difference_serialise_et_voit_les_champs_disparus(self):
        self.assertEqual(
            difference({"a": 1, "b": 2}, {"a": 1, "c": 3}),
            {"c": [None, 3], "b": [2, None]},
        )
