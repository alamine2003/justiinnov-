"""Le journal d'audit et l'historique ne se modifient ni ne s'effacent, même en base."""

from django.db import DatabaseError, transaction
from django.test import TestCase

from core.models import ChangeLog, Country
from expenses.models import AuditLog


class JournalImmuableTests(TestCase):
    def setUp(self):
        self.pays = Country.objects.create(
            name="Togo", code="TG", country_ref="TG-01", currency="XOF",
            timezone="Africa/Lome",
        )
        self.entree = AuditLog.objects.create(
            user="siege", action=AuditLog.Action.DOWNLOADED, object_type="Export",
            object_id=None, label="Export", country=self.pays,
        )

    def _refuse(self, operation):
        # Le déclencheur lève une exception PostgreSQL ; Django la remonte en
        # DatabaseError, quelle que soit sa sous-classe exacte.
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                operation()

    def test_une_entree_d_audit_ne_se_modifie_pas(self):
        self._refuse(lambda: AuditLog.objects.filter(pk=self.entree.pk).update(label="Falsifié"))
        self.entree.refresh_from_db()
        self.assertEqual(self.entree.label, "Export")

    def test_une_entree_d_audit_ne_s_efface_pas(self):
        self._refuse(lambda: AuditLog.objects.filter(pk=self.entree.pk).delete())
        self.assertTrue(AuditLog.objects.filter(pk=self.entree.pk).exists())

    def test_l_historique_ne_se_modifie_ni_ne_s_efface(self):
        # La création du pays a laissé une entrée d'historique.
        entree = ChangeLog.objects.filter(model_name=ChangeLog.Models.COUNTRY).first()
        self.assertIsNotNone(entree)
        self._refuse(lambda: ChangeLog.objects.filter(pk=entree.pk).update(performed_by="x"))
        self._refuse(lambda: ChangeLog.objects.filter(pk=entree.pk).delete())
        self.assertTrue(ChangeLog.objects.filter(pk=entree.pk).exists())
