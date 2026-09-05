"""Jeu de démonstration pour l'intégration continue et les captures d'écran.

    python manage.py seed_demo --base-jetable

Crée, en une transaction, de quoi remplir chaque écran : deux pays (Togo,
Côte d'Ivoire), leurs enveloppes de l'exercice courant, équipes, managers,
projets, bénéficiaires, un taux de change, et quatre dossiers togolais à
des états variés — brouillon, soumis, justifié en partie, non justifié —
avec leurs lignes et une pièce PDF minimale. Un dossier a été rouvert puis
resoumis, pour que la fiche montre un motif de réouverture.

Rien n'est inséré à la main : le référentiel passe par l'ORM et ses signaux
d'historique, les dossiers par les mêmes services que l'application
(``expenses.transitions`` : soumission, justification, constat,
réouverture) et le dépôt de pièce par sa vue. Le journal d'audit,
l'historique et les notifications sont donc ceux que ces actions produisent
réellement, pas des lignes fabriquées.

Les actions sont signées par trois comptes de démonstration — ``demo.pays``
(manager du Togo), ``demo.controle`` (DF), ``demo.direction`` (super
administrateur) — créés **sans mot de passe utilisable** et sans adresse :
ils ne peuvent pas se connecter et ne reçoivent aucun e-mail. Ils existent
parce que la règle des quatre yeux exige deux personnes, et parce qu'une
trace d'audit dit *qui* a agi.

La commande est **idempotente et n'efface rien** : si le dossier de
démonstration existe déjà, elle ne fait rien et le dit. Il n'y a pas
d'option ``--reset`` — rien ne se supprime dans cette application, pas même
une démonstration ; une base de démonstration se recrée, elle ne se vide
pas. Elle est prévue pour une base jetable (CI, captures), pas pour la
production : comme rien ne se supprime, deux pays et quatre dossiers de
démonstration lancés par mégarde sur une base réelle y resteraient. Le
drapeau ``--base-jetable`` est donc obligatoire ; sans lui, la commande
refuse avant d'avoir rien écrit.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import Role, UserProfile
from accounts.permissions import get_access
from budget.aggregates import convert
from budget.models import Budget, ExchangeRate
from core.journal import Trace
from core.models import Country, Manager, Project, Team
from core.regles import PermissionRefusee, RegleViolee
from core.requetes import reset_current_request, set_current_request
from expenses import transitions
from expenses.audit import record
from expenses.models import AuditLog, Beneficiary, Dossier, Expense
from expenses.views import ProofViewSet
from expenses.workflow import Status
from reporting.scope import fuseau_de

#: Signature des entrées d'historique du référentiel.
ACTEUR = "seed_demo"

#: N°ORDRE du premier dossier : sa présence signe un jeu déjà en place.
TEMOIN = "DEMO-0001"

PAYS = [
    {
        "code": "TG", "name": "Togo", "country_ref": "TG-01", "currency": "XOF",
        "currency_symbol": "FCFA", "timezone": "Africa/Lome",
    },
    {
        "code": "CI", "name": "Côte d'Ivoire", "country_ref": "CI-01", "currency": "XOF",
        "currency_symbol": "FCFA", "timezone": "Africa/Abidjan",
    },
]

EQUIPES = {"TG": ["Équipe Lomé", "Équipe Kara"], "CI": ["Équipe Abidjan"]}
MANAGERS = {"TG": "Kodjo Mensah", "CI": "Awa Koné"}
PROJETS = {"TG": "Lancement gamme pédiatrique", "CI": "Salon pharmaceutique d'Abidjan"}
BENEFICIAIRES = {
    "TG": ("Pharmacie du Grand Marché", Beneficiary.Kind.CLIENT),
    "CI": ("Clinique des Deux Plateaux", Beneficiary.Kind.PROSPECT),
}
ENVELOPPES = {"TG": Decimal("25000000.00"), "CI": Decimal("30000000.00")}
SOUS_ENVELOPPE_LOME = Decimal("8000000.00")

COMPTES = {
    "demo.pays": (Role.MANAGER, "TG"),
    "demo.controle": (Role.DF, None),
    "demo.direction": (Role.SUPER_ADMIN, None),
}


class Command(BaseCommand):
    help = "Crée un jeu de démonstration idempotent (deux pays, quatre dossiers)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-jetable",
            action="store_true",
            help="Confirme que la base est jetable (CI, captures) : rien ne "
                 "se supprime, un jeu de démonstration y resterait.",
        )

    def handle(self, *args, **options):
        if not options["base_jetable"]:
            raise CommandError(
                "seed_demo écrit deux pays et quatre dossiers de démonstration "
                "qui ne se suppriment pas : réservé à une base jetable. "
                "Relancez avec --base-jetable si c'est bien le cas."
            )
        if Dossier.objects.filter(number=TEMOIN, country__code="TG").exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Jeu de démonstration déjà en place ({TEMOIN}) : rien à faire."
                )
            )
            return

        # Les signaux d'historique lisent l'utilisateur de la requête
        # courante ; il n'y en a pas ici. Une pseudo-requête signée par la
        # commande évite des entrées anonymes.
        jeton = set_current_request(
            SimpleNamespace(
                user=SimpleNamespace(username=ACTEUR, is_authenticated=True),
                META={},
            )
        )
        try:
            with transaction.atomic():
                self._creer()
        finally:
            reset_current_request(jeton)
        self.stdout.write(self.style.SUCCESS("Jeu de démonstration créé."))

    # -- Référentiel --------------------------------------------------------

    def _creer(self):
        self.annee = timezone.now().year
        self.pays = {p["code"]: self._pays(p) for p in PAYS}
        self.equipes = {}
        self.managers = {}
        self.projets = {}
        for code, country in self.pays.items():
            for nom in EQUIPES[code]:
                self.equipes[nom], _ = Team.objects.get_or_create(country=country, name=nom)
            manager = country.managers.filter(name=MANAGERS[code]).first()
            if manager is None:
                manager = Manager.objects.create(name=MANAGERS[code], title="Manager pays")
                country.managers.add(manager)
            self.managers[code] = manager
            self.projets[code], _ = Project.objects.get_or_create(
                country=country, name=PROJETS[code],
                defaults={"status": "active", "budget": Decimal("5000000.00")},
            )
            nom, kind = BENEFICIAIRES[code]
            Beneficiary.objects.get_or_create(
                country=country, name=nom, defaults={"kind": kind}
            )
            Budget.objects.get_or_create(
                country=country, year=self.annee, project=None, team=None, manager=None,
                defaults={"amount": ENVELOPPES[code]},
            )
        Budget.objects.get_or_create(
            country=self.pays["TG"], year=self.annee, team=self.equipes["Équipe Lomé"],
            project=None, manager=None, defaults={"amount": SOUS_ENVELOPPE_LOME},
        )
        ExchangeRate.objects.get_or_create(
            currency="EUR", valid_from=datetime(self.annee, 1, 1).date(),
            defaults={"rate_to_xof": Decimal("655.957000")},
        )

        self.comptes = {nom: self._compte(nom, *COMPTES[nom]) for nom in COMPTES}
        self._dossiers()

    def _pays(self, payload):
        """Le pays, tel qu'il existe déjà — ``seed_users`` peut l'avoir créé."""
        country = Country.objects.filter(code=payload["code"]).first()
        if country is None:
            country = Country.objects.create(**payload)
        return country

    def _compte(self, username, role, code_pays):
        """Compte de démonstration : actif, sans mot de passe ni adresse."""
        user = User.objects.filter(username=username).first()
        if user is None:
            user = User.objects.create_user(username=username, email="", password=None)
        profile = getattr(user, "profile", None)
        if profile is None:
            profile = UserProfile.objects.create(
                user=user, role=role, must_change_password=False
            )
        if code_pays:
            profile.countries.add(self.pays[code_pays])
        return user

    # -- Dossiers -----------------------------------------------------------

    def _dossiers(self):
        togo = self.pays["TG"]
        lome, kara = self.equipes["Équipe Lomé"], self.equipes["Équipe Kara"]
        manager = self.managers["TG"]
        projet = self.projets["TG"]
        pays_user = self.comptes["demo.pays"]
        controle = self.comptes["demo.controle"]
        direction = self.comptes["demo.direction"]

        # Brouillon : en cours de saisie, sans pièce.
        brouillon = self._dossier(
            TEMOIN, "Tournée des officines de Lomé", togo, lome, manager, jours=5,
            lignes=[
                ("Carburant véhicule de tournée", "85000.00", {}),
                ("Déjeuner avec les pharmaciens", "42500.00", {"beneficiary": True}),
            ],
        )

        # Soumis : rouvert une fois par la direction, corrigé, resoumis.
        soumis = self._dossier(
            "DEMO-0002", "Formation des délégués de Kara", togo, kara, manager, jours=20,
            lignes=[
                ("Location de la salle", "250000.00", {}),
                ("Pause-café des participants", "60000.00", {}),
                ("Supports de formation imprimés", "138000.00", {"project": projet}),
            ],
        )
        self._piece(soumis, pays_user)
        self._action("submit", soumis, pays_user)
        self._action(
            "reopen", soumis, direction,
            note="La facture de la salle est illisible : merci d'en déposer une lisible.",
        )
        self._piece(soumis, pays_user, version=2)
        self._action("submit", soumis, pays_user)

        # Justifié en partie : une ligne couverte, l'autre à moitié.
        partiel = self._dossier(
            "DEMO-0003", "Lancement gamme pédiatrique — Lomé", togo, lome, manager,
            jours=45,
            lignes=[
                ("Stand et affichage", "480000.00", {"project": projet}),
                ("Échantillons et goodies", "215000.00", {"project": projet}),
                ("Hébergement du formateur (payé en euros)", None, {"euros": "150.00"}),
            ],
        )
        self._piece(partiel, pays_user)
        self._action("submit", partiel, pays_user)
        lignes = list(partiel.expenses.order_by("pk"))
        self._action("justify", lignes[0], controle)
        self._action(
            "justify", lignes[1], controle,
            justified_amount=Decimal("100000.00"),
            note="Reçu partiel : le solde reste à prouver.",
        )

        # Non justifié : le siège a constaté l'absence de preuve.
        non_justifie = self._dossier(
            "DEMO-0004", "Frais de représentation — Kara", togo, kara, manager, jours=90,
            lignes=[("Réception des grossistes", "320000.00", {"beneficiary": True})],
        )
        self._action("submit", non_justifie, pays_user)
        self._action(
            "reject", non_justifie.expenses.get(), controle,
            note="Aucune facture ni décharge fournie après relance.",
        )
        del brouillon

    def _dossier(self, number, label, country, team, manager, *, jours, lignes):
        """Un dossier et ses lignes, datés dans le fuseau du pays, tracés."""
        pays_user = self.comptes["demo.pays"]
        fuseau = fuseau_de(country)
        # Les dates restent dans l'exercice courant : une ligne de l'année
        # passée n'aurait pas d'enveloppe où s'imputer.
        plancher = datetime.combine(datetime(self.annee, 1, 2).date(), time(9), tzinfo=fuseau)
        quand = max(timezone.now().astimezone(fuseau) - timedelta(days=jours), plancher)
        dossier = Dossier.objects.create(
            number=number, label=label, country=country, team=team, owner=manager,
            date=quand.date(), status=Status.DRAFT, created_by=pays_user.username,
        )
        record(self._trace(pays_user), AuditLog.Action.CREATED, dossier)
        beneficiaire = Beneficiary.objects.filter(country=country).first()
        for rang, (titre, montant, options) in enumerate(lignes):
            champs = {
                "dossier": dossier, "country": country, "team": team, "owner": manager,
                "date": quand + timedelta(hours=rang), "title": titre,
                "status": Status.DRAFT, "created_by": pays_user.username,
                "project": options.get("project"),
                "beneficiary": beneficiaire if options.get("beneficiary") else None,
                "place": "Lomé" if team.name == "Équipe Lomé" else "Kara",
            }
            if montant is not None:
                champs["amount"] = Decimal(montant)
            else:
                # Décaissement en devise (§5.3) : le montant en FCFA vient de
                # la conversion au taux du jour, figé sur la ligne.
                origine = Decimal(options["euros"])
                converti, taux = convert(origine, "EUR", country.currency, quand.date())
                if converti is None:
                    raise CommandError("Aucun taux EUR → XOF : la ligne en euros ne se convertit pas.")
                champs.update(
                    amount=converti, original_currency="EUR",
                    original_amount=origine, original_rate=taux,
                )
            expense = Expense.objects.create(**champs)
            record(self._trace(pays_user), AuditLog.Action.CREATED, expense)
        return dossier

    def _piece(self, dossier, user, version=1):
        """Dépose une pièce PDF par la vue, comme le ferait le pays."""
        contenu = _pdf(f"Justificatif {dossier.number} — version {version}", dossier.label)
        donnees = {
            "dossier": dossier.pk,
            "kind": "invoice",
            "file": SimpleUploadedFile(
                f"facture-{dossier.number.lower()}-v{version}.pdf", contenu,
                content_type="application/pdf",
            ),
        }
        if version > 1:
            precedente = dossier.proofs.order_by("-version").first()
            donnees["replaces"] = precedente.pk
        requete = self._requete(user, "post", "/api/proofs/", donnees, format="multipart")
        self._verifier(ProofViewSet.as_view({"post": "create"})(requete), "dépôt de pièce")

    def _action(self, nom, instance, user, **donnees):
        """Joue une transition par le service : verrou, audit, notification.

        Les règles refusent par exception (``core.regles``) ; un refus est
        une erreur de la commande, pas un état à rattraper.
        """
        try:
            transitions.executer(
                instance, nom, get_access(user), self._trace(user), **donnees
            )
        except (RegleViolee, PermissionRefusee) as exc:
            raise CommandError(f"Échec de l'action « {nom} » : {exc}") from exc
        instance.refresh_from_db()

    @staticmethod
    def _trace(user):
        """Signature des écritures : l'auteur, sans adresse — il n'y a pas
        de requête."""
        return Trace.depuis_compte(user)

    def _requete(self, user, methode="get", chemin="/", donnees=None, **extra):
        """Requête signée par ``user``, pour la vue de dépôt de pièce.

        ``127.0.0.1`` figure toujours dans ``ALLOWED_HOSTS`` ; ``testserver``,
        le défaut de la fabrique, pas nécessairement.
        """
        fabrique = APIRequestFactory(SERVER_NAME="127.0.0.1")
        requete = getattr(fabrique, methode)(chemin, donnees, **extra)
        force_authenticate(requete, user=user)
        return requete

    def _verifier(self, reponse, action):
        if reponse.status_code >= 400:
            raise CommandError(
                f"Échec de l'action « {action} » ({reponse.status_code}) : {reponse.data}"
            )
        return reponse


def _pdf(titre, sous_titre):
    """Une page PDF, lisible par n'importe quel lecteur, propre à chaque pièce."""
    tampon = BytesIO()
    page = canvas.Canvas(tampon, pagesize=A4)
    page.setTitle(titre)
    page.setFont("Helvetica-Bold", 16)
    page.drawString(72, 770, titre)
    page.setFont("Helvetica", 11)
    page.drawString(72, 745, sous_titre)
    page.drawString(72, 725, "Document de démonstration — sans valeur probante.")
    page.showPage()
    page.save()
    return tampon.getvalue()
