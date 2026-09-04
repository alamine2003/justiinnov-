"""Tests de l'historisation automatique (``core.signals``)."""

from django.test import TestCase

from core.models import ChangeLog, CostCenter, Country, Manager, Team


class ChangeLogTestCase(TestCase):
    """Base commune : deux pays et une équipe rattachée au premier."""

    def setUp(self):
        self.ghana = Country.objects.create(
            name="Ghana", code="GH", currency="GHS", timezone="Africa/Accra"
        )
        self.senegal = Country.objects.create(
            name="Sénégal", code="SN", currency="XOF", timezone="Africa/Dakar"
        )
        self.team = Team.objects.create(country=self.ghana, name="Équipe Nord")
        ChangeLog.objects.all().delete()

    def entries(self, **filters):
        return ChangeLog.objects.filter(**filters).order_by("id")


class CreationTests(ChangeLogTestCase):
    def test_creation_est_journalisee(self):
        Team.objects.create(country=self.senegal, name="Équipe Sud")

        entry = self.entries(action=ChangeLog.Actions.CREATED).get()
        self.assertEqual(entry.model_name, ChangeLog.Models.TEAM)
        self.assertEqual(entry.country, self.senegal)

    def test_creation_de_pays_est_rattachee_au_pays(self):
        """Sans rattachement, l'événement serait invisible dans l'historique
        du pays (``/api/history/?country={id}``)."""
        mali = Country.objects.create(
            name="Mali", code="ML", currency="XOF", timezone="Africa/Bamako"
        )

        entry = self.entries(action=ChangeLog.Actions.CREATED).get()
        self.assertEqual(entry.country, mali)

    def test_manager_sans_pays(self):
        Manager.objects.create(name="Awa Diop")

        entry = self.entries(action=ChangeLog.Actions.CREATED).get()
        self.assertEqual(entry.model_name, ChangeLog.Models.MANAGER)
        self.assertIsNone(entry.country)


class UpdateTests(ChangeLogTestCase):
    def test_mise_a_jour_simple(self):
        self.team.name = "Équipe Nord-Est"
        self.team.save()

        entry = self.entries(action=ChangeLog.Actions.UPDATED).get()
        self.assertEqual(entry.changed_fields, ["name"])
        self.assertIn("Équipe Nord", entry.from_value)
        self.assertIn("Équipe Nord-Est", entry.to_value)

    def test_sauvegarde_sans_changement_ne_journalise_rien(self):
        self.team.save()

        self.assertFalse(self.entries().exists())

    def test_desactivation_puis_reactivation_d_un_pays(self):
        self.ghana.is_active = False
        self.ghana.save()
        self.ghana.is_active = True
        self.ghana.save()

        actions = list(self.entries().values_list("action", flat=True))
        self.assertEqual(
            actions,
            [ChangeLog.Actions.DEACTIVATED, ChangeLog.Actions.REACTIVATED],
        )
        # Rattachées au pays, donc visibles dans son onglet « Historique ».
        self.assertEqual(self.entries().first().country, self.ghana)

    def test_changement_de_rattachement(self):
        self.team.country = self.senegal
        self.team.save()

        entry = self.entries(action=ChangeLog.Actions.REASSIGNED).get()
        self.assertEqual(entry.from_value, "Ghana (GH)")
        self.assertEqual(entry.country, self.senegal)

    def test_rattachement_et_autre_champ_modifies_ensemble(self):
        """Régression : le rattachement masquait la mise à jour des autres
        champs, qui n'était alors jamais journalisée."""
        self.team.country = self.senegal
        self.team.name = "Équipe Sud"
        self.team.save()

        actions = list(self.entries().values_list("action", flat=True))
        self.assertEqual(
            actions,
            [ChangeLog.Actions.REASSIGNED, ChangeLog.Actions.UPDATED],
        )
        update = self.entries(action=ChangeLog.Actions.UPDATED).get()
        self.assertEqual(update.changed_fields, ["name"])

    def test_desactivation_et_autre_champ_modifies_ensemble(self):
        self.ghana.is_active = False
        self.ghana.timezone = "Europe/Lyon"
        self.ghana.save()

        actions = list(self.entries().values_list("action", flat=True))
        self.assertEqual(
            actions,
            [ChangeLog.Actions.DEACTIVATED, ChangeLog.Actions.UPDATED],
        )
        self.assertEqual(
            self.entries(action=ChangeLog.Actions.UPDATED).get().changed_fields,
            ["timezone"],
        )


class DeletionTests(ChangeLogTestCase):
    def test_suppression_est_journalisee(self):
        self.team.delete()

        entry = self.entries(action=ChangeLog.Actions.DELETED).get()
        self.assertEqual(entry.model_name, ChangeLog.Models.TEAM)
        self.assertEqual(entry.country, self.ghana)
        self.assertIn("Équipe Nord", entry.from_value)
        self.assertEqual(entry.to_value, "")

    def test_suppression_en_cascade_d_un_pays(self):
        """Les entités filles doivent être journalisées sans référence à un
        pays supprimé (sinon violation de clé étrangère)."""
        CostCenter.objects.create(country=self.ghana, code="CC01", name="Paris")
        ChangeLog.objects.all().delete()

        self.ghana.delete()

        deleted = self.entries(action=ChangeLog.Actions.DELETED)
        self.assertEqual(
            set(deleted.values_list("model_name", flat=True)),
            {
                ChangeLog.Models.TEAM,
                ChangeLog.Models.COST_CENTER,
                ChangeLog.Models.COUNTRY,
            },
        )
        # Aucune entrée ne pointe vers le pays supprimé.
        self.assertFalse(deleted.filter(country__isnull=False).exists())


class DiffEtAdresseTests(ChangeLogTestCase):
    """Chaque entrée dit ce qui a changé, et depuis où."""

    def test_le_diff_porte_les_anciennes_et_nouvelles_valeurs(self):
        self.team.name = "Équipe Nord-Est"
        self.team.description = "Kumasi"
        self.team.save()

        entry = self.entries(action=ChangeLog.Actions.UPDATED).get()
        self.assertEqual(
            entry.diff,
            {"name": ["Équipe Nord", "Équipe Nord-Est"], "description": ["", "Kumasi"]},
        )

    def test_le_rattachement_porte_les_identifiants(self):
        self.team.country = self.senegal
        self.team.save()

        entry = self.entries(action=ChangeLog.Actions.REASSIGNED).get()
        self.assertEqual(entry.diff, {"country": [self.ghana.pk, self.senegal.pk]})

    def test_hors_requete_ni_auteur_ni_adresse(self):
        self.team.name = "Équipe Nord-Est"
        self.team.save()

        entry = self.entries(action=ChangeLog.Actions.UPDATED).get()
        self.assertEqual(entry.performed_by, "")
        self.assertIsNone(entry.ip_address)

    def test_la_requete_courante_signe_l_entree(self):
        from types import SimpleNamespace

        from core.signals import get_current_request, reset_current_request, set_current_request

        requete = SimpleNamespace(
            user=SimpleNamespace(username="awa", is_authenticated=True),
            META={"REMOTE_ADDR": "198.51.100.4"},
        )
        jeton = set_current_request(requete)
        try:
            self.team.name = "Équipe Nord-Est"
            self.team.save()
        finally:
            reset_current_request(jeton)

        entry = self.entries(action=ChangeLog.Actions.UPDATED).get()
        self.assertEqual(entry.performed_by, "awa")
        self.assertEqual(entry.ip_address, "198.51.100.4")
        # Le contexte est rendu : rien ne fuit vers l'écriture suivante.
        self.assertIsNone(get_current_request())

    def test_les_valeurs_non_json_sont_converties(self):
        from decimal import Decimal

        from core.signals import serialisable

        self.assertEqual(serialisable(Decimal("12.50")), "12.50")
        self.assertEqual(serialisable(self.team.created_at), self.team.created_at.isoformat())
        self.assertEqual(serialisable([1, Decimal("2")]), [1, "2"])
        self.assertIsNone(serialisable(None))


class ManagersDuPaysTests(ChangeLogTestCase):
    """Changer le responsable d'un pays est un rattachement : il se journalise."""

    def setUp(self):
        super().setUp()
        self.awa = Manager.objects.create(name="Awa Diop")
        self.kofi = Manager.objects.create(name="Kofi Mensah")
        ChangeLog.objects.all().delete()

    def test_ajout_d_un_manager(self):
        self.ghana.managers.add(self.awa)

        entry = self.entries(model_name=ChangeLog.Models.COUNTRY).get()
        self.assertEqual(entry.action, ChangeLog.Actions.UPDATED)
        self.assertEqual(entry.country, self.ghana)
        self.assertEqual(entry.changed_fields, ["managers"])
        self.assertEqual(entry.diff, {"managers": [[], ["Awa Diop"]]})

    def test_remplacement_des_managers(self):
        self.ghana.managers.add(self.awa)
        ChangeLog.objects.all().delete()

        self.ghana.managers.set([self.kofi])

        diffs = [e.diff["managers"] for e in self.entries()]
        self.assertEqual(diffs[0][0], ["Awa Diop"])
        self.assertEqual(diffs[-1][1], ["Kofi Mensah"])

    def test_vidage_des_managers(self):
        self.ghana.managers.set([self.awa, self.kofi])
        ChangeLog.objects.all().delete()

        self.ghana.managers.clear()

        entry = self.entries().get()
        self.assertEqual(entry.diff, {"managers": [["Awa Diop", "Kofi Mensah"], []]})

    def test_depuis_le_manager(self):
        """``manager.countries.add(pays)`` se lit dans l'historique du pays."""
        self.awa.countries.add(self.ghana)

        entry = self.entries(model_name=ChangeLog.Models.COUNTRY).get()
        self.assertEqual(entry.country, self.ghana)
        self.assertEqual(entry.diff, {"managers": [[], ["Awa Diop"]]})

    def test_sans_changement_rien(self):
        self.ghana.managers.add(self.awa)
        ChangeLog.objects.all().delete()

        self.ghana.managers.add(self.awa)

        self.assertFalse(self.entries().exists())
