"""Une période en bornes rend exactement ce que rendait ``__date`` (décision 123)."""

from datetime import UTC, date, datetime, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import ChangeLog
from core.periodes import entre_les_jours
from expenses.filtres import AuditLogFilter, ElementSupprimeFilter
from expenses.models import AuditLog, ElementSupprime
from notifications.models import Notification


class EntreLesJoursTests(TestCase):
    """Autour de minuit, dans un fuseau à l'est et un à l'ouest de Greenwich :
    c'est là qu'une borne mal prise ferait entrer ou sortir une ligne."""

    @classmethod
    def setUpTestData(cls):
        cls.personne = User.objects.create(username="periode")
        # Toutes les demi-heures autour de trois minuits UTC.
        instants = [
            datetime(2026, 3, jour, 0, 0, tzinfo=UTC) + timedelta(minutes=30 * pas)
            for jour in (14, 15, 16)
            for pas in range(-10, 11)
        ]
        for rang, instant in enumerate(instants):
            notification = Notification.objects.create(
                recipient=cls.personne, kind="proof_missing", title="p", dedup_key=f"p-{rang}",
            )
            Notification.objects.filter(pk=notification.pk).update(created_at=instant)

    def _comparer(self, debut, fin):
        tous = Notification.objects.all()
        attendu = tous
        if debut:
            attendu = attendu.filter(created_at__date__gte=debut)
        if fin:
            attendu = attendu.filter(created_at__date__lte=fin)
        obtenu = tous.filter(entre_les_jours("created_at", debut, fin))
        self.assertEqual(
            sorted(obtenu.values_list("pk", flat=True)),
            sorted(attendu.values_list("pk", flat=True)),
        )
        return obtenu.count()

    def test_memes_lignes_dans_chaque_fuseau(self):
        for fuseau in ("UTC", "Africa/Djibouti", "America/Port-au-Prince"):
            with self.subTest(fuseau=fuseau), override_settings(TIME_ZONE=fuseau), \
                    timezone.override(fuseau):
                for debut, fin in [
                    (date(2026, 3, 15), date(2026, 3, 15)),
                    (date(2026, 3, 14), date(2026, 3, 15)),
                    (date(2026, 3, 15), None),
                    (None, date(2026, 3, 14)),
                ]:
                    self._comparer(debut, fin)

    def test_un_jour_borne_inclus_des_deux_cotes(self):
        with override_settings(TIME_ZONE="UTC"), timezone.override("UTC"):
            # Le 15 en UTC : les 11 instants de 0 h à 5 h, et les 10 de
            # 19 h à 23 h 30 — ni le 14 à 23 h 30, ni le 16 à 0 h.
            self.assertEqual(self._comparer(date(2026, 3, 15), date(2026, 3, 15)), 21)

    def test_les_bords_du_calendrier_ne_levent_rien(self):
        self.assertEqual(self._comparer(date.min, date.max), Notification.objects.count())


class FiltresDePeriodeTests(TestCase):
    """Les filtres d'API ``?debut=`` et ``?fin=`` des journaux et de la corbeille."""

    def test_le_dernier_jour_du_calendrier_est_accepte(self):
        for filtre, queryset in (
            (AuditLogFilter, AuditLog.objects.all()),
            (ElementSupprimeFilter, ElementSupprime.objects.all()),
        ):
            with self.subTest(filtre=filtre.__name__):
                resultat = filtre(
                    data={"debut": "0001-01-01", "fin": "9999-12-31"}, queryset=queryset
                ).qs
                self.assertEqual(list(resultat), list(queryset))

    def test_le_filtre_s_ecrit_en_bornes(self):
        sql = str(AuditLogFilter(data={"debut": "2026-03-01", "fin": "2026-03-31"},
                                 queryset=AuditLog.objects.all()).qs.query)
        self.assertNotIn("AT TIME ZONE", sql)
        self.assertIn('"created_at" >=', sql)
        self.assertIn('"created_at" <', sql)

    def test_l_historique_s_ecrit_en_bornes(self):
        from accounts.referentiel import ChangeLogFilter

        sql = str(ChangeLogFilter(data={"debut": "2026-03-01"},
                                  queryset=ChangeLog.objects.all()).qs.query)
        self.assertNotIn("AT TIME ZONE", sql)
