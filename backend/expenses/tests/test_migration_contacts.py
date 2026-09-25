"""Reprise des contacts des bénéficiaires (décision 93, ``expenses.0018``).

Le texte libre « Contact » passe dans le champ qui lui revient quand il
**est** un e-mail ou un numéro ; tout autre texte reste où il était.
"""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

AVANT = [("expenses", "0017_brouillons_du_siege_rendus_au_pays")]
APRES = [("expenses", "0018_contacts_des_beneficiaires")]


class RepriseDesContactsTests(TransactionTestCase):
    def _migrer(self, cible):
        executor = MigrationExecutor(connection)
        executor.migrate(cible)
        executor.loader.build_graph()
        return executor.loader.project_state(cible).apps

    def test_chaque_contact_va_dans_son_champ_et_rien_ne_se_perd(self):
        apps = self._migrer(AVANT)
        try:
            Country = apps.get_model("core", "Country")
            Beneficiary = apps.get_model("expenses", "Beneficiary")
            togo = Country.objects.create(
                name="Togo", code="TG", country_ref="TG-01", currency="XOF",
                timezone="Africa/Lome",
            )
            for nom, contact in (
                ("Par e-mail", " pharmacie@exemple.org "),
                ("Par téléphone", "+228  90 12 34 56"),
                ("En texte libre", "M. Diallo, 90 12 34 56"),
                ("Sans contact", ""),
            ):
                Beneficiary.objects.create(country=togo, name=nom, contact=contact)

            apps = self._migrer(APRES)
            Beneficiary = apps.get_model("expenses", "Beneficiary")
            lu = {
                b.name: (b.phone, b.email, b.contact)
                for b in Beneficiary.objects.all()
            }

            self.assertEqual(lu["Par e-mail"], ("", "pharmacie@exemple.org", ""))
            self.assertEqual(lu["Par téléphone"], ("+228 90 12 34 56", "", ""))
            self.assertEqual(lu["En texte libre"], ("", "", "M. Diallo, 90 12 34 56"))
            self.assertEqual(lu["Sans contact"], ("", "", ""))
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
