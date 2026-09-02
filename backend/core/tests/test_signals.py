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
