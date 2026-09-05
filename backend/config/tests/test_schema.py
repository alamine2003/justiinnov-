"""Le contrat d'API : généré sans avertissement, servi au siège seulement."""

import io
import json

from django.core.management import call_command
from django.test import override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role
from accounts.tests.test_scoping import make_user


class GenerationDuSchemaTests(APITestCase):
    def test_le_schema_se_genere_sans_avertissement(self):
        """Un avertissement de drf-spectacular signale un champ ou une vue
        que le schéma ne sait pas typer : le frontend recevrait ``string``
        là où le serveur rend un objet. La commande échoue alors, comme en
        CI (``--fail-on-warn``)."""
        sortie = io.StringIO()
        call_command(
            "spectacular", "--format", "openapi-json", "--validate",
            "--fail-on-warn", stdout=sortie,
        )
        document = json.loads(sortie.getvalue())

        self.assertEqual(document["info"]["title"], "JUSTI INNOV")
        self.assertIn("/api/dossiers/{id}/submit/", document["paths"])
        self.assertNotIn("/api/schema/ui/", document["paths"])

    def test_les_reponses_declarent_tous_leurs_champs(self):
        """DRF rend chaque champ d'un sérialiseur : le contrat le dit, sauf
        l'avertissement d'une transition, absent quand il n'y a rien à dire."""
        sortie = io.StringIO()
        call_command("spectacular", "--format", "openapi-json", stdout=sortie)
        composants = json.loads(sortie.getvalue())["components"]["schemas"]

        expense = composants["Expense"]
        self.assertEqual(sorted(expense["required"]), sorted(expense["properties"]))
        transition = composants["DossierTransitionResponse"]
        self.assertIn("warning", transition["properties"])
        self.assertNotIn("warning", transition["required"])
        # En requête, ce qui est facultatif le reste.
        self.assertNotIn("amount", composants["ExpenseRequest"].get("required", []))

    def test_les_champs_calcules_sont_types(self):
        """Sans ``@extend_schema_field``, un champ calculé serait ``string``."""
        sortie = io.StringIO()
        call_command("spectacular", "--format", "openapi-json", stdout=sortie)
        composants = json.loads(sortie.getvalue())["components"]["schemas"]

        def reference(champ):
            # Un composant imbriqué en lecture seule est enveloppé dans ``allOf``.
            return champ["allOf"][0]["$ref"]

        self.assertEqual(reference(composants["Me"]["properties"]["permissions"]), "#/components/schemas/Permissions")
        self.assertEqual(composants["Me"]["properties"]["supervision"]["type"], "boolean")
        self.assertEqual(reference(composants["Budget"]["properties"]["figures"]), "#/components/schemas/BudgetFigures")
        self.assertEqual(reference(composants["Budget"]["properties"]["scope_kind"]), "#/components/schemas/BudgetScopeEnum")
        self.assertEqual(composants["Dossier"]["properties"]["allowed_actions"]["type"], "array")
        self.assertEqual(composants["ChangeLog"]["properties"]["changed_fields"]["type"], "array")
        self.assertEqual(composants["AuditLog"]["properties"]["detail"]["type"], "object")
        self.assertEqual(composants["Configuration"]["properties"]["supervision"]["type"], "boolean")


class AccesAuSchemaTests(APITestCase):
    """Le schéma est une carte de la plateforme : le siège la lit, pas le pays."""

    def _connecter(self, role, **kwargs):
        user = make_user(f"schema.{role}", role, [], **kwargs)
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return user

    def test_anonyme_refuse(self):
        self.assertEqual(self.client.get("/api/schema/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_le_siege_lit_le_schema(self):
        for role in (Role.SUPER_ADMIN, Role.ADMIN, Role.DF, Role.DM):
            with self.subTest(role=role):
                self._connecter(role)
                response = self.client.get("/api/schema/?format=json")
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertIn("/api/expenses/", json.loads(response.content)["paths"])

    def test_le_pays_ne_lit_pas_le_schema(self):
        self._connecter(Role.MANAGER)
        self.assertEqual(self.client.get("/api/schema/").status_code, status.HTTP_403_FORBIDDEN)

    def test_l_interface_n_existe_pas_hors_debug(self):
        self._connecter(Role.SUPER_ADMIN)
        with override_settings(DEBUG=False):
            self.assertEqual(self.client.get("/api/schema/ui/").status_code, status.HTTP_404_NOT_FOUND)

    def test_l_interface_est_reservee_aux_administrateurs(self):
        with override_settings(DEBUG=True):
            self._connecter(Role.DF)
            self.assertEqual(self.client.get("/api/schema/ui/").status_code, status.HTTP_403_FORBIDDEN)
            self._connecter(Role.ADMIN)
            response = self.client.get("/api/schema/ui/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn(b"swagger-ui", response.content)
