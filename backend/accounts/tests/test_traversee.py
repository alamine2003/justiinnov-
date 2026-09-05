"""Traversée du cloisonnement : chaque route du routeur, chaque périmètre.

Décision 39. Plutôt qu'un test par vue, écrit à la main et oublié à la
suivante, les cas sont engendrés depuis les routeurs des applications : pour
chaque viewset, sa liste, son détail et ses actions de détail. Le décor porte,
par modèle, un objet ivoirien, un objet togolais d'une autre équipe et un
objet togolais de l'équipe du manager. Un manager du Togo rattaché à une
équipe ne lit (200 sans l'objet, ou 404) et n'écrit rien d'ivoirien ni d'une
autre équipe ; un DF restreint au Togo ne lit rien d'ivoirien.

Un viewset dont le modèle n'est ni dans le décor ni déclaré sans périmètre
fait échouer le test : une nouvelle ressource se classe, elle ne s'oublie pas.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.tests.test_scoping import ScopingTestCase, make_user
from budget.models import Budget, BudgetReallocation, ExchangeRate
from core.models import (
    ChangeLog,
    CostCenter,
    Country,
    ExpenseTitle,
    Manager,
    MarketingCategory,
    Project,
    Team,
)
from expenses.models import AuditLog, Beneficiary, Dossier, Expense, Proof
from expenses.tests.base import in_memory_storage
from notifications.models import Notification

#: Modèles exposés par un viewset sans périmètre de pays : un taux de change
#: vaut pour tout le monde. Tout autre modèle doit figurer dans le décor.
SANS_PERIMETRE = {ExchangeRate}

#: Réponses acceptables pour un objet hors périmètre : introuvable, ou
#: refusé par le rôle avant même d'être cherché. Jamais 200, jamais 400 —
#: une erreur de validation dirait que l'objet existe.
HORS_PERIMETRE = {403, 404, 405}


def _routeurs():
    from accounts.urls import router as accounts_router
    from budget.urls import router as budget_router
    from expenses.urls import router as expenses_router
    from notifications.urls import router as notifications_router

    for routeur in (accounts_router, budget_router, expenses_router, notifications_router):
        yield from routeur.registry


def _identifiants(charge):
    """Identifiants présents dans une réponse de liste, paginée ou non."""
    if isinstance(charge, dict) and "results" in charge:
        charge = charge["results"]
    if not isinstance(charge, list):
        return set()
    return {ligne.get("id") for ligne in charge if isinstance(ligne, dict)}


@in_memory_storage
class TraverseeDuCloisonnementTests(ScopingTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.team_kara = Team.objects.create(country=cls.togo, name="Équipe Kara")
        cls.rep = make_user("lome.innov", Role.MANAGER, [cls.togo], teams=[cls.team_togo])
        cls.rep_ivoire = make_user("abidjan.innov", Role.MANAGER, [cls.ivoire])
        cls.rep_kara = make_user("kara.innov", Role.MANAGER, [cls.togo], teams=[cls.team_kara])
        cls.df_togo = make_user("df.togo", Role.DF, [cls.togo])
        cls.decor = cls._planter()

    @classmethod
    def _planter(cls):
        """Le décor : par modèle, ``ivoire``, ``autre_equipe`` et ``mien``.

        ``autre_equipe`` est ``None`` pour une ressource qui ne porte pas
        d'équipe ; ``mien`` sert à vérifier que la route répond bien à ce
        qui est dans le périmètre, pour qu'un 404 ne cache pas une route
        cassée.
        """
        annee = timezone.now().year
        managers = {
            "ivoire": Manager.objects.create(name="Awa Diallo"),
            "mien": Manager.objects.create(name="Kodjo Mensah"),
        }
        managers["ivoire"].countries.add(cls.ivoire)
        managers["mien"].countries.add(cls.togo)

        def par_pays(modele, **champs):
            return {
                "ivoire": modele.objects.create(country=cls.ivoire, **champs),
                "autre_equipe": None,
                "mien": modele.objects.create(country=cls.togo, **champs),
            }

        projets = par_pays(Project, name="Projet")
        budgets = par_pays(Budget, year=annee, amount=Decimal("1000.00"))
        sous_budgets = {
            cle: Budget.objects.create(
                country=budget.country, year=annee, amount=Decimal("10.00"),
                project=projets[cle],
            )
            for cle, budget in budgets.items() if budget is not None
        }
        reallocations = {
            cle: BudgetReallocation.objects.create(
                source=budget, target=sous_budgets[cle], amount=Decimal("1.00"),
                reason="Renfort", requested_by="seed",
            ) if budget is not None else None
            for cle, budget in budgets.items()
        }

        def dossier(number, country, team):
            return Dossier.objects.create(
                number=number, label=number, country=country, team=team,
                owner=managers["ivoire" if country == cls.ivoire else "mien"],
                date=date(annee, 3, 1), created_by="seed",
            )

        dossiers = {
            "ivoire": dossier("CI-1", cls.ivoire, cls.team_ivoire),
            "autre_equipe": dossier("TG-2", cls.togo, cls.team_kara),
            "mien": dossier("TG-1", cls.togo, cls.team_togo),
        }
        depenses = {
            cle: Expense.objects.create(
                dossier=d, country=d.country, team=d.team, owner=d.owner,
                date=timezone.now(), title="Carburant", amount=Decimal("5.00"),
                created_by="seed",
            )
            for cle, d in dossiers.items()
        }
        pieces = {
            cle: Proof.objects.create(
                dossier=d, file=ContentFile(b"%PDF-1.4", name=f"{cle}.pdf"),
                original_name=f"{cle}.pdf", kind=Proof.Kind.INVOICE,
                sha256=f"{cle:0<64}"[:64], size=8, content_type="application/pdf",
                uploaded_by="seed",
            )
            for cle, d in dossiers.items()
        }
        journaux = {
            cle: AuditLog.objects.create(
                user="seed", action=AuditLog.Action.CREATED, object_type="Dossier",
                object_id=d.pk, label=d.number, country=d.country,
            )
            for cle, d in dossiers.items()
        }
        historique = {
            "ivoire": ChangeLog.objects.create(
                model_name=ChangeLog.Models.TEAM, action=ChangeLog.Actions.CREATED,
                label="Abidjan", country=cls.ivoire, object_id=cls.team_ivoire.pk,
            ),
            "autre_equipe": None,
            "mien": ChangeLog.objects.create(
                model_name=ChangeLog.Models.TEAM, action=ChangeLog.Actions.CREATED,
                label="Lomé", country=cls.togo, object_id=cls.team_togo.pk,
            ),
        }

        def notification(recipient, country):
            return Notification.objects.create(
                recipient=recipient, kind=Notification.Kind.PROOF_MISSING,
                level=Notification.Level.INFO, title="Info", country=country,
            )

        return {
            Country: {"ivoire": cls.ivoire, "autre_equipe": None, "mien": cls.togo},
            Manager: {**managers, "autre_equipe": None},
            Team: {"ivoire": cls.team_ivoire, "autre_equipe": cls.team_kara, "mien": cls.team_togo},
            CostCenter: par_pays(CostCenter, code="CC", name="Centre"),
            Project: projets,
            ExpenseTitle: par_pays(ExpenseTitle, label="Carburant"),
            MarketingCategory: par_pays(MarketingCategory, name="Salon"),
            ChangeLog: historique,
            User: {"ivoire": cls.rep_ivoire, "autre_equipe": cls.rep_kara, "mien": cls.rep},
            Budget: budgets,
            BudgetReallocation: reallocations,
            Beneficiary: par_pays(Beneficiary, name="Client"),
            Dossier: dossiers,
            Expense: depenses,
            Proof: pieces,
            AuditLog: journaux,
            # Une notification appartient à une personne : le « mien » du DF
            # n'est pas celui du manager.
            Notification: {
                "ivoire": notification(cls.rep_ivoire, cls.ivoire),
                "autre_equipe": notification(cls.rep_kara, cls.togo),
                "mien": notification(cls.rep, cls.togo),
                "mien_df": notification(cls.df_togo, cls.togo),
            },
        }

    # -- Génération des cas -------------------------------------------------

    def _cas(self):
        """(préfixe, nom de base, viewset, décor) pour chaque viewset cloisonné."""
        for prefixe, viewset, basename in _routeurs():
            modele = viewset.queryset.model
            if modele in SANS_PERIMETRE:
                continue
            self.assertIn(
                modele, self.decor,
                f"Le viewset « {prefixe} » expose {modele.__name__} : à classer dans "
                "le décor de la traversée, ou dans SANS_PERIMETRE.",
            )
            yield prefixe, basename, viewset, self.decor[modele]

    def _charge_etrangere(self, cle):
        """Une charge utile qui ne nomme que des objets hors périmètre."""
        def pk(modele):
            objet = self.decor[modele].get(cle)
            return objet.pk if objet is not None else None

        return {
            champ: valeur for champ, valeur in {
                "country": pk(Country), "team": pk(Team), "project": pk(Project),
                "manager": pk(Manager), "owner": pk(Manager), "dossier": pk(Dossier),
                "budget": pk(Budget), "source": pk(Budget), "target": pk(Budget),
                "replaces": pk(Proof), "beneficiary": pk(Beneficiary),
                "countries": [pk(Country)], "teams": [pk(Team)],
            }.items() if valeur not in (None, [None])
        }

    def _etrangers(self, decor, cles):
        return [(cle, decor[cle]) for cle in cles if decor.get(cle) is not None]

    # -- Le manager cloisonné -----------------------------------------------

    def test_un_manager_cloisonne_ne_lit_rien_hors_de_son_equipe(self):
        self.login(self.rep)
        for prefixe, basename, viewset, decor in self._cas():
            etrangers = self._etrangers(decor, ("ivoire", "autre_equipe"))
            with self.subTest(route=f"{prefixe}/", action="list"):
                reponse = self.client.get(reverse(f"{basename}-list"))
                self.assertIn(reponse.status_code, (200, 403))
                if reponse.status_code == 200:
                    ids = _identifiants(reponse.data)
                    for cle, objet in etrangers:
                        self.assertNotIn(objet.pk, ids, f"{prefixe} liste l'objet {cle}")
            for cle, objet in etrangers:
                with self.subTest(route=f"{prefixe}/{{pk}}/", action="retrieve", objet=cle):
                    reponse = self.client.get(reverse(f"{basename}-detail", kwargs={"pk": objet.pk}))
                    self.assertIn(reponse.status_code, HORS_PERIMETRE)
                    if reponse.status_code == 404:
                        # Le 404 vient du périmètre, pas d'une route cassée.
                        mien = self.client.get(
                            reverse(f"{basename}-detail", kwargs={"pk": decor["mien"].pk})
                        )
                        self.assertEqual(mien.status_code, 200, f"{prefixe} ne rend pas le mien")
            for action in viewset.get_extra_actions():
                if not action.detail or "get" not in action.mapping:
                    continue
                for cle, objet in etrangers:
                    with self.subTest(route=f"{prefixe}/{{pk}}/{action.url_path}/", objet=cle):
                        reponse = self.client.get(
                            reverse(f"{basename}-{action.url_name}", kwargs={"pk": objet.pk})
                        )
                        self.assertIn(reponse.status_code, HORS_PERIMETRE)

    def test_un_manager_cloisonne_n_ecrit_rien_hors_de_son_equipe(self):
        self.login(self.rep)
        for prefixe, basename, viewset, decor in self._cas():
            modele = viewset.queryset.model
            etrangers = self._etrangers(decor, ("ivoire", "autre_equipe"))
            for cle, objet in etrangers:
                detail = reverse(f"{basename}-detail", kwargs={"pk": objet.pk})
                for methode in ("patch", "put", "delete"):
                    with self.subTest(route=f"{prefixe}/{{pk}}/", methode=methode, objet=cle):
                        reponse = getattr(self.client, methode)(detail, {}, format="json")
                        self.assertIn(reponse.status_code, HORS_PERIMETRE)
                for action in viewset.get_extra_actions():
                    if not action.detail:
                        continue
                    for methode in action.mapping:
                        if methode == "get":
                            continue
                        with self.subTest(route=f"{prefixe}/{{pk}}/{action.url_path}/", methode=methode, objet=cle):
                            reponse = getattr(self.client, methode)(
                                reverse(f"{basename}-{action.url_name}", kwargs={"pk": objet.pk}),
                                {}, format="json",
                            )
                            self.assertIn(reponse.status_code, HORS_PERIMETRE)
                with self.subTest(route=f"{prefixe}/", methode="post", objet=cle):
                    avant = modele.objects.count()
                    reponse = self.client.post(
                        reverse(f"{basename}-list"), self._charge_etrangere(cle), format="json"
                    )
                    self.assertNotIn(reponse.status_code, (200, 201))
                    self.assertEqual(modele.objects.count(), avant, f"{prefixe} a créé chez {cle}")

    # -- Le DF restreint ----------------------------------------------------

    def test_un_df_restreint_ne_lit_rien_d_un_autre_pays(self):
        self.login(self.df_togo)
        for prefixe, basename, viewset, decor in self._cas():
            ivoire = decor["ivoire"]
            with self.subTest(route=f"{prefixe}/", action="list"):
                reponse = self.client.get(reverse(f"{basename}-list"))
                self.assertIn(reponse.status_code, (200, 403))
                if reponse.status_code == 200:
                    self.assertNotIn(ivoire.pk, _identifiants(reponse.data), f"{prefixe} liste l'ivoirien")
            with self.subTest(route=f"{prefixe}/{{pk}}/", action="retrieve"):
                reponse = self.client.get(reverse(f"{basename}-detail", kwargs={"pk": ivoire.pk}))
                self.assertIn(reponse.status_code, HORS_PERIMETRE)
                if reponse.status_code == 404:
                    mien = self.client.get(
                        reverse(
                            f"{basename}-detail",
                            kwargs={"pk": decor.get("mien_df", decor["mien"]).pk},
                        )
                    )
                    self.assertEqual(mien.status_code, 200, f"{prefixe} ne rend pas le togolais")
            for action in viewset.get_extra_actions():
                if not action.detail or "get" not in action.mapping:
                    continue
                with self.subTest(route=f"{prefixe}/{{pk}}/{action.url_path}/"):
                    reponse = self.client.get(
                        reverse(f"{basename}-{action.url_name}", kwargs={"pk": ivoire.pk})
                    )
                    self.assertIn(reponse.status_code, HORS_PERIMETRE)

    def test_le_decor_couvre_tous_les_viewsets(self):
        modeles = {viewset.queryset.model for _, viewset, _ in _routeurs()}
        self.assertEqual(modeles - SANS_PERIMETRE - set(self.decor), set())
        self.assertEqual(SANS_PERIMETRE - modeles, set(), "SANS_PERIMETRE cite un modèle sans viewset")
