"""La primitive de cloisonnement (décision 39) : une règle, lue des deux côtés."""

from datetime import date

from django.contrib.auth.models import User
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import Role
from accounts.perimetre import ChampCloisonne, comptes_couvrant, filtrer
from accounts.permissions import get_access
from accounts.tests.test_scoping import ScopingTestCase, make_user
from core.models import Country, Manager, Team
from expenses.models import Dossier


class FiltrerTests(ScopingTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.team_kara = Team.objects.create(country=cls.togo, name="Équipe Kara")
        cls.manager = Manager.objects.create(name="Kodjo Mensah")
        cls.manager.countries.add(cls.togo)
        cls.dossiers = {
            "ivoire": cls._dossier("CI-1", cls.ivoire, cls.team_ivoire),
            "lome": cls._dossier("TG-1", cls.togo, cls.team_togo),
            "kara": cls._dossier("TG-2", cls.togo, cls.team_kara),
            "sans_equipe": cls._dossier("TG-3", cls.togo, None),
        }
        cls.rep_lome = make_user("lome", Role.MANAGER, [cls.togo], teams=[cls.team_togo])
        cls.rep_kara = make_user("kara", Role.MANAGER, [cls.togo], teams=[cls.team_kara])
        cls.df_togo = make_user("df.togo", Role.DF, [cls.togo])
        cls.sans_profil = User.objects.create_user("orphelin", password="x")

    @classmethod
    def _dossier(cls, number, country, team):
        return Dossier.objects.create(
            number=number, label=number, country=country, team=team,
            date=date(2026, 3, 1), created_by="seed",
        )

    def _visibles(self, user, **options):
        acces = get_access(user)
        return set(filtrer(Dossier.objects.all(), acces, **options).values_list("number", flat=True))

    def test_le_siege_global_voit_tout(self):
        self.assertEqual(self._visibles(self.siege, equipe="team"), {"CI-1", "TG-1", "TG-2", "TG-3"})

    def test_un_compte_restreint_ne_voit_que_ses_pays(self):
        self.assertEqual(self._visibles(self.df_togo, equipe="team"), {"TG-1", "TG-2", "TG-3"})

    def test_un_manager_sans_equipe_voit_tout_son_pays(self):
        self.assertEqual(self._visibles(self.rep_togo, equipe="team"), {"TG-1", "TG-2", "TG-3"})

    def test_un_manager_cloisonne_ne_voit_que_ses_equipes(self):
        """Règle en vigueur : une entité sans équipe lui échappe aussi."""
        self.assertEqual(self._visibles(self.rep_lome, equipe="team"), {"TG-1"})
        self.assertEqual(self._visibles(self.rep_kara, equipe="team"), {"TG-2"})

    def test_sans_chemin_d_equipe_la_ressource_se_lit_par_pays(self):
        self.assertEqual(self._visibles(self.rep_lome), {"TG-1", "TG-2", "TG-3"})

    def test_sans_droits_rien(self):
        self.assertEqual(self._visibles(self.sans_profil), set())
        self.assertEqual(set(filtrer(Dossier.objects.all(), None)), set())

    def test_distinct_sur_un_chemin_multiple(self):
        """Un manager rattaché à deux pays du périmètre ne sort qu'une fois."""
        self.manager.countries.add(self.ivoire)
        deux_pays = make_user("df.deux", Role.DF, [self.togo, self.ivoire])
        managers = filtrer(
            Manager.objects.all(), get_access(deux_pays), pays="countries", distinct=True
        )
        self.assertEqual(list(managers), [self.manager])

    def test_comptes_couvrant_est_la_reciproque_de_filtrer(self):
        """Qui voit un dossier (``filtrer``) est exactement qui en est
        prévenu (``comptes_couvrant``), pour chaque compte et chaque dossier
        porteur d'une équipe."""
        comptes = [
            self.rep_togo, self.rep_lome, self.rep_kara, self.df_togo,
            self.siege, self.controleur, self.dm,
        ]
        for nom in ("ivoire", "lome", "kara"):
            dossier = self.dossiers[nom]
            prevenus = set(
                comptes_couvrant(
                    User.objects.filter(pk__in=[c.pk for c in comptes]),
                    dossier.country, dossier.team,
                )
            )
            for compte in comptes:
                with self.subTest(dossier=nom, compte=compte.username):
                    voit = filtrer(
                        Dossier.objects.filter(pk=dossier.pk), get_access(compte), equipe="team"
                    ).exists()
                    self.assertEqual(compte in prevenus, voit)

    @staticmethod
    def _choix(user, champ):
        """Ce que ``champ`` propose à ``user``, monté dans un sérialiseur.

        Le champ lit la requête dans le contexte de son sérialiseur parent,
        comme en service : pas d'attribut privé de DRF posé à la main.
        """
        brute = APIRequestFactory().post("/")
        force_authenticate(brute, user=user)

        class Formulaire(serializers.Serializer):
            x = champ

        serializer = Formulaire(context={"request": Request(brute)})
        return serializer.fields["x"].get_queryset()

    def test_champ_cloisonne_ne_propose_que_le_perimetre(self):
        def choix(user, **options):
            champ = ChampCloisonne(queryset=Dossier.objects.all(), chemin_pays="country", **options)
            return set(self._choix(user, champ).values_list("number", flat=True))

        self.assertEqual(choix(self.rep_lome), {"TG-1", "TG-2", "TG-3"})
        self.assertEqual(choix(self.rep_lome, chemin_equipe="team"), {"TG-1"})
        self.assertEqual(choix(self.df_togo, chemin_equipe="team"), {"TG-1", "TG-2", "TG-3"})
        self.assertEqual(choix(self.sans_profil), set())

    def test_champ_cloisonne_sur_le_pays_lui_meme(self):
        champ = ChampCloisonne(queryset=Country.objects.all(), chemin_pays="pk")
        self.assertEqual(list(self._choix(self.df_togo, champ)), [self.togo])
