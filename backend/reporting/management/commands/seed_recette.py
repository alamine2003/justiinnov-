"""Jeu de recette : les dix-sept filiales, les trois rôles, chaque état du circuit.

    docker compose exec backend python manage.py seed_recette --base-jetable

À quoi il sert. `seed_demo` remplit deux pays pour les captures de la CI, avec
des comptes qui ne se connectent pas. Celui-ci prépare une **recette
manuelle** : une personne se connecte tour à tour avec chaque compte et
vérifie ce que l'application lui montre et lui permet. Le guide qui va avec
est `docs/recette.md`.

Ce qu'il crée, en une transaction :

- les **dix-sept pays** de `core/africa.py`, chacun dans **sa** devise
  (FCFA ouest et centre, ariary, franc guinéen, ouguiya, dalasi, franc de
  Djibouti, franc congolais) et son fuseau, avec deux équipes, un manager du
  référentiel, un projet, un client et un prospect ;
- par pays, une enveloppe et une sous-enveloppe d'équipe, calibrées pour que
  le tableau de bord montre les trois niveaux : la plupart des pays à l'aise,
  le Sénégal, le Cameroun et Madagascar en alerte, la Guinée et la RDC en
  dépassement, et le Mali en politique « bloquer » : son manager ne pourra
  pas soumettre son brouillon, c'est voulu ;
- des taux de change **fictifs**, dont un taux en euros daté du mois
  prochain : il doit s'afficher « historique » tant qu'il n'est pas en
  vigueur ;
- **trente-six comptes connectables** : deux au siège — la DG, super
  administratrice, qui supervise, et la RH, administratrice, qui contrôle
  (décision 89) — et, par pays, un manager du pays entier et un manager
  restreint à une équipe ;
- par pays, **huit dossiers** qui couvrent le circuit : deux brouillons (dont
  un d'un collègue, que le manager du pays ne doit pas pouvoir soumettre),
  un soumis, un en contrôle, un justifié en partie avec une ligne payée en
  euros, un non justifié sans pièce, un clôturé avec une **demande de
  rectification en attente**, un rouvert puis resoumis ;
- trois **réallocations** au Togo (une en attente, une approuvée, une
  refusée) et une en attente au Sénégal et au Cameroun.

Tout passe par les services de l'application (`expenses.transitions`,
`budget.transitions`, la vue de dépôt de pièce) : le journal d'audit,
l'historique et les notifications sont ceux que ces actions produisent
vraiment. Les décisions laissées **en attente** — mise en contrôle,
justification, rectification, réallocation — sont celles que la recette
prend elle-même.

Les comptes partagent un mot de passe tiré au sort à la première exécution,
affiché une fois et écrit dans `recette.local.md` (ignoré par git). Leurs
adresses sont en `@innovpharma.net`, comme l'exige la plateforme : la pile
locale n'a pas de serveur de courrier, les e-mails vont dans les journaux
du conteneur et ne partent nulle part.

GARDE-FOUS. Rien ne se supprime dans cette application : un jeu de recette
lancé sur une base réelle y resterait. La commande exige `--base-jetable`
**et** le mode debug (`DJANGO_DEBUG=1`, celui de la pile locale) ; la
production et la préproduction tournent sans, et refusent avant d'avoir rien
écrit. Le jeu se retire en jetant la base, jamais par l'application :
`docker compose down -v` (docs/recette.md, « Tout retirer »).
"""

import secrets
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import Role, UserProfile, aligner_drapeaux
from accounts.permissions import get_access
from budget import transitions as enveloppes
from budget.aggregates import convert
from budget.models import Budget, ExchangeRate, OverrunPolicy
from core.journal import Trace
from core.models import Country, Manager, Project, Team
from core.regles import HorsPerimetre, PermissionRefusee, RegleViolee
from core.requetes import reset_current_request, set_current_request
from expenses import transitions
from expenses.audit import record
from expenses.models import AuditLog, Beneficiary, Dossier, Expense
from expenses.services import committed_total
from expenses.views import ProofViewSet
from expenses.workflow import CONSUMING_STATUSES, Status
from reporting.management.commands.seed_demo import _pdf
from reporting.scope import fuseau_de

ACTEUR = "seed_recette"
TEMOIN = "R-TG-01"
PREFIXE = "recette"
DOMAINE = "innovpharma.net"
FICHIER = Path(__file__).resolve().parents[3] / "recette.local.md"

#: Code ISO → (nom, devise, symbole, fuseau, (équipe 1, équipe 2)).
PAYS = {
    "SN": ("Sénégal", "XOF", "FCFA", "Africa/Dakar", ("Dakar", "Thiès")),
    "ML": ("Mali", "XOF", "FCFA", "Africa/Bamako", ("Bamako", "Sikasso")),
    "CI": ("Côte d'Ivoire", "XOF", "FCFA", "Africa/Abidjan", ("Abidjan", "Bouaké")),
    "MG": ("Madagascar", "MGA", "Ar", "Indian/Antananarivo", ("Antananarivo", "Toamasina")),
    "CM": ("Cameroun", "XAF", "FCFA", "Africa/Douala", ("Douala", "Yaoundé")),
    "GA": ("Gabon", "XAF", "FCFA", "Africa/Libreville", ("Libreville", "Port-Gentil")),
    "MR": ("Mauritanie", "MRU", "UM", "Africa/Nouakchott", ("Nouakchott", "Nouadhibou")),
    "BF": ("Burkina Faso", "XOF", "FCFA", "Africa/Ouagadougou", ("Ouagadougou", "Bobo-Dioulasso")),
    "NE": ("Niger", "XOF", "FCFA", "Africa/Niamey", ("Niamey", "Zinder")),
    "BJ": ("Bénin", "XOF", "FCFA", "Africa/Porto-Novo", ("Cotonou", "Parakou")),
    "GN": ("Guinée", "GNF", "FG", "Africa/Conakry", ("Conakry", "Kankan")),
    "TG": ("Togo", "XOF", "FCFA", "Africa/Lome", ("Lomé", "Kara")),
    "GM": ("Gambie", "GMD", "D", "Africa/Banjul", ("Banjul", "Serekunda")),
    "DJ": ("Djibouti", "DJF", "Fdj", "Africa/Djibouti", ("Djibouti", "Ali Sabieh")),
    "TD": ("Tchad", "XAF", "FCFA", "Africa/Ndjamena", ("N'Djamena", "Moundou")),
    "CG": ("Congo", "XAF", "FCFA", "Africa/Brazzaville", ("Brazzaville", "Pointe-Noire")),
    "CD": ("République démocratique du Congo", "CDF", "FC", "Africa/Kinshasa", ("Kinshasa", "Lubumbashi")),
}

#: FCFA pour une unité. **Taux fictifs de recette**, arrondis, sans valeur
#: officielle ; seule la parité de l'euro (655,957) est exacte.
TAUX = {
    "EUR": Decimal("655.957"), "XAF": Decimal("1"), "MGA": Decimal("0.13"),
    "GNF": Decimal("0.07"), "MRU": Decimal("15.5"), "GMD": Decimal("8.8"),
    "DJF": Decimal("3.4"), "CDF": Decimal("0.21"),
}

#: Niveau d'exécution visé, en part consommée de chaque enveloppe.
EN_ALERTE = {"SN": Decimal("0.93"), "CM": Decimal("0.95"), "MG": Decimal("0.92")}
EN_DEPASSEMENT = {"GN": Decimal("1.15"), "CD": Decimal("1.25")}
#: Politique « bloquer » : le brouillon du manager dépasserait l'enveloppe.
BLOQUE = "ML"

#: Siège : identifiant → (rôle, pays ou None pour tous, libellé). Le siège
#: voit toujours tous les pays.
SIEGE = {
    "dg": (Role.SUPER_ADMIN, None, "Direction générale"),
    "rh": (Role.ADMIN, None, "Ressources humaines"),
}

#: Les huit dossiers d'un pays. Montants en FCFA d'équivalent, convertis dans
#: la devise du pays. `equipe` : 0 ou 1 ; `auteur` : manager du pays ou de
#: l'équipe. Les lignes en euros portent un montant en EUR.
DOSSIERS = [
    ("01", "Tournée des officines", 1, "pays", 5,
     [("Carburant véhicule de tournée", 85000, None), ("Déjeuner avec les pharmaciens", 42500, "client")]),
    ("02", "Impression des supports de visite", 0, "equipe", 3,
     [("Impression des plaquettes", 60000, None)]),
    ("03", "Formation des délégués", 0, "pays", 12,
     [("Location de la salle", 250000, None), ("Pause-café des participants", 60000, None)]),
    ("04", "Congrès régional de pédiatrie", 1, "pays", 18,
     [("Transport des délégués", 180000, None), ("Hébergement", 95000, None)]),
    ("05", "Lancement de la gamme pédiatrique", 0, "pays", 40,
     [("Stand et affichage", 480000, "projet"), ("Échantillons et goodies", 215000, "projet"),
      ("Hébergement du formateur (payé en euros)", "150.00", "euros")]),
    ("06", "Frais de représentation", 1, "pays", 70,
     [("Réception des grossistes", 320000, "client")]),
    ("07", "Location de véhicule — trimestre", 0, "pays", 95,
     [("Location du véhicule", 140000, None), ("Péages", 75000, None)]),
    ("08", "Séminaire des prescripteurs", 1, "pays", 30,
     [("Supports imprimés", 138000, "projet"), ("Traiteur", 90000, "prospect")]),
]


class Command(BaseCommand):
    help = "Remplit une base jetable pour la recette : 17 pays, 40 comptes, 136 dossiers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-jetable", action="store_true",
            help="Confirme que la base est jetable : rien ne s'y supprime ensuite.",
        )

    def handle(self, *args, **options):
        if not options["base_jetable"]:
            raise CommandError(
                "seed_recette écrit dix-sept pays, quarante comptes et des centaines "
                "de lignes qui ne se suppriment pas : réservé à une base jetable. "
                "Relancez avec --base-jetable si c'est bien le cas."
            )
        if not settings.DEBUG:
            raise CommandError(
                "seed_recette refuse de tourner hors du mode debug : la production et "
                "la préproduction tournent sans, et un jeu de recette y resterait pour "
                "toujours. Utilisez la pile locale (docker compose up -d)."
            )
        if Dossier.objects.filter(number=TEMOIN, country__code="TG").exists():
            self.stdout.write(self.style.WARNING(
                f"Jeu de recette déjà en place ({TEMOIN}) : rien à faire. "
                f"Les comptes et le mot de passe sont dans {FICHIER.name}."
            ))
            return

        self.mot_de_passe = secrets.token_urlsafe(9)
        jeton = set_current_request(SimpleNamespace(
            user=SimpleNamespace(username=ACTEUR, is_authenticated=True), META={},
        ))
        try:
            with transaction.atomic():
                self._creer()
        finally:
            reset_current_request(jeton)
        self._rapport()

    # -- Référentiel -----------------------------------------------------------

    def _creer(self):
        self.annee = timezone.now().year
        self.jour = timezone.now().date()
        self._taux()
        self.pays, self.equipes, self.gens, self.projets, self.benefs = {}, {}, {}, {}, {}
        self.enveloppes = {}
        for code, (nom, devise, symbole, fuseau, villes) in PAYS.items():
            country = Country.objects.filter(code=code).first() or Country.objects.create(
                code=code, name=nom, country_ref=f"{code}-01", currency=devise,
                currency_symbol=symbole, timezone=fuseau,
            )
            self.pays[code] = country
            self.equipes[code] = [
                Team.objects.get_or_create(country=country, name=f"Équipe {ville}")[0]
                for ville in villes
            ]
            gens = country.managers.filter(name=f"Responsable {nom}").first()
            if gens is None:
                gens = Manager.objects.create(name=f"Responsable {nom}", title="Manager pays")
                country.managers.add(gens)
            self.gens[code] = gens
            self.projets[code] = Project.objects.get_or_create(
                country=country, name=f"Gamme pédiatrique — {nom}",
                defaults={"status": "active", "budget": self._local(5_000_000, country)},
            )[0]
            self.benefs[code] = {
                "client": Beneficiary.objects.get_or_create(
                    country=country, name=f"Pharmacie centrale de {villes[0]}",
                    defaults={"kind": Beneficiary.Kind.CLIENT})[0],
                "prospect": Beneficiary.objects.get_or_create(
                    country=country, name=f"Clinique de {villes[1]}",
                    defaults={"kind": Beneficiary.Kind.PROSPECT})[0],
            }
            politique = OverrunPolicy.BLOCK if code == BLOQUE else OverrunPolicy.WARN
            # Larges d'abord : chaque soumission doit passer. Les niveaux
            # d'alerte se calibrent une fois les dossiers joués (`_calibrer`).
            self.enveloppes[code] = {
                "pays": Budget.objects.create(
                    country=country, year=self.annee, amount=self._local(30_000_000, country),
                    overrun_policy=politique),
                "equipe": Budget.objects.create(
                    country=country, year=self.annee, team=self.equipes[code][0],
                    amount=self._local(10_000_000, country), overrun_policy=politique),
            }
        self._comptes()
        for code in PAYS:
            self._dossiers(code)
        self._reallocations()
        self._calibrer()

    def _taux(self):
        debut = date(self.annee, 1, 1)
        for devise, taux in TAUX.items():
            ExchangeRate.objects.get_or_create(
                currency=devise, valid_from=debut, defaults={"rate_to_xof": taux})
        # Un taux daté du mois prochain : il ne doit pas être « en vigueur ».
        prochain = (self.jour.replace(day=1) + timedelta(days=32)).replace(day=1)
        ExchangeRate.objects.get_or_create(
            currency="EUR", valid_from=prochain, defaults={"rate_to_xof": Decimal("656.000")})

    def _local(self, fcfa, country):
        """Un montant en FCFA d'équivalent, exprimé dans la devise du pays."""
        taux = TAUX.get(country.currency, Decimal("1"))
        return (Decimal(fcfa) / taux).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    def _comptes(self):
        self.comptes = {}
        for suffixe, (role, codes, _libelle) in SIEGE.items():
            pays = [self.pays[c] for c in codes] if codes else []
            self.comptes[suffixe] = self._compte(suffixe, role, pays)
        for code in PAYS:
            cc = code.lower()
            self.comptes[f"{cc}.manager"] = self._compte(
                f"{cc}.manager", Role.MANAGER, [self.pays[code]], gens=self.gens[code])
            self.comptes[f"{cc}.equipe"] = self._compte(
                f"{cc}.equipe", Role.MANAGER, [self.pays[code]],
                equipes=[self.equipes[code][0]], gens=self.gens[code])

    def _compte(self, suffixe, role, pays, equipes=(), gens=None):
        username = f"{PREFIXE}.{suffixe}"
        user = User.objects.filter(username=username).first()
        if user is None:
            user = User.objects.create_user(
                username=username, email=f"{username}@{DOMAINE}", password=self.mot_de_passe,
                first_name="Recette", last_name=suffixe.upper(),
            )
        profile = getattr(user, "profile", None) or UserProfile.objects.create(
            user=user, role=role, must_change_password=False)
        profile.countries.set(pays)
        profile.teams.set(equipes)
        if gens is not None:
            profile.manager = gens
            profile.save(update_fields=["manager"])
        aligner_drapeaux(user, role)
        return user

    # -- Dossiers --------------------------------------------------------------

    def _dossiers(self, code):
        country = self.pays[code]
        cc = code.lower()
        manager, equipe = self.comptes[f"{cc}.manager"], self.comptes[f"{cc}.equipe"]
        # Le contrôle, de bout en bout, est à l'administrateur (décision 89).
        rh = self.comptes["rh"]
        d = {}
        for rang, titre, idx_equipe, auteur, jours, lignes in DOSSIERS:
            d[rang] = self._dossier(
                f"R-{code}-{rang}", f"{titre} — {country.name}", country,
                self.equipes[code][idx_equipe], equipe if auteur == "equipe" else manager,
                jours, lignes,
            )

        # 03 — soumis, avec pièce : attend la mise en contrôle.
        self._piece(d["03"], manager)
        self._action("submit", d["03"], manager)

        # 04 — en contrôle : attend la décision de l'administrateur.
        self._piece(d["04"], manager)
        self._action("submit", d["04"], manager)
        self._action("review", d["04"], rh)

        # 05 — justifié en partie ; la ligne en euros reste en contrôle.
        self._piece(d["05"], manager)
        self._action("submit", d["05"], manager)
        self._action("review", d["05"], rh)
        stand, echantillons, _euros = d["05"].expenses.order_by("pk")
        self._action("justify", stand, rh)
        self._action("justify", echantillons, rh,
                     justified_amount=(echantillons.amount / 2).quantize(Decimal("1")),
                     note="Reçu partiel : le solde reste à prouver.")

        # 06 — non justifié, soumis sans pièce.
        self._action("submit", d["06"], manager)
        self._action("review", d["06"], rh)
        self._action("reject", d["06"].expenses.get(), rh,
                     note="Aucune facture ni décharge fournie après relance.")
        self._action("reject", d["06"], rh,
                     note="Dossier constaté non justifié : aucune pièce fournie.")

        # 07 — clôturé, puis une rectification demandée par le pays.
        self._piece(d["07"], manager)
        self._action("submit", d["07"], manager)
        self._action("review", d["07"], rh)
        for ligne in d["07"].expenses.order_by("pk"):
            self._action("justify", ligne, rh)
        self._action("justify", d["07"], rh)
        self._action("close", d["07"], rh)
        try:
            transitions.demander_rectification(
                d["07"].expenses.order_by("pk").first(), get_access(manager),
                "La facture de location porte le mauvais numéro de véhicule : à revoir.",
                Trace.depuis_compte(manager),
            )
        except (RegleViolee, PermissionRefusee, HorsPerimetre) as exc:
            raise CommandError(f"Rectification impossible ({code}) : {exc}") from exc

        # 08 — rouvert par la RH pour une pièce illisible, corrigé, resoumis.
        self._piece(d["08"], manager)
        self._action("submit", d["08"], manager)
        self._action("reopen", d["08"], rh,
                     note="La facture du traiteur est illisible : merci d'en déposer une lisible.")
        self._piece(d["08"], manager, version=2)
        self._action("submit", d["08"], manager)
        self.dossiers_du_pays = d

    def _dossier(self, number, label, country, team, auteur, jours, lignes):
        fuseau = fuseau_de(country)
        plancher = datetime.combine(date(self.annee, 1, 3), time(9), tzinfo=fuseau)
        quand = max(timezone.now().astimezone(fuseau) - timedelta(days=jours), plancher)
        code = country.code
        dossier = Dossier.objects.create(
            number=number, label=label, country=country, team=team, owner=self.gens[code],
            date=quand.date(), status=Status.DRAFT, created_by=auteur.username,
        )
        record(Trace.depuis_compte(auteur), AuditLog.Action.CREATED, dossier)
        for rang, (titre, montant, genre) in enumerate(lignes):
            champs = {
                "dossier": dossier, "country": country, "team": team, "owner": self.gens[code],
                "date": quand + timedelta(hours=rang), "title": titre, "status": Status.DRAFT,
                "created_by": auteur.username, "place": team.name.removeprefix("Équipe "),
                "project": self.projets[code] if genre == "projet" else None,
                "beneficiary": self.benefs[code].get(genre),
            }
            if genre == "euros":
                origine = Decimal(montant)
                converti, taux = convert(origine, "EUR", country.currency, quand.date())
                if converti is None:
                    raise CommandError(f"Aucun taux EUR → {country.currency}.")
                champs.update(amount=converti, original_currency="EUR",
                              original_amount=origine, original_rate=taux)
            else:
                champs["amount"] = self._local(montant, country)
            record(Trace.depuis_compte(auteur), AuditLog.Action.CREATED,
                   Expense.objects.create(**champs))
        return dossier

    def _piece(self, dossier, user, version=1):
        donnees = {
            "dossier": dossier.pk, "kind": "invoice",
            "file": SimpleUploadedFile(
                f"facture-{dossier.number.lower()}-v{version}.pdf",
                _pdf(f"Justificatif {dossier.number} — version {version}", dossier.label),
                content_type="application/pdf"),
        }
        if version > 1:
            donnees["replaces"] = dossier.proofs.order_by("-version").first().pk
        requete = APIRequestFactory(SERVER_NAME="127.0.0.1").post(
            "/api/proofs/", donnees, format="multipart")
        force_authenticate(requete, user=user)
        reponse = ProofViewSet.as_view({"post": "create"})(requete)
        if reponse.status_code >= 400:
            raise CommandError(f"Dépôt de pièce refusé ({dossier.number}) : {reponse.data}")

    def _action(self, nom, instance, user, **donnees):
        try:
            transitions.executer(instance, nom, get_access(user),
                                 Trace.depuis_compte(user), **donnees)
        except (RegleViolee, PermissionRefusee, HorsPerimetre) as exc:
            raise CommandError(f"Action « {nom} » refusée sur {instance} : {exc}") from exc
        instance.refresh_from_db()

    # -- Enveloppes ------------------------------------------------------------

    def _reallocations(self):
        dg, rh = self.comptes["dg"], self.comptes["rh"]
        motif = "Renfort de l'équipe pour la campagne de visites du trimestre."
        demandes = {}
        for code in ("TG", "SN", "CM"):
            env = self.enveloppes[code]
            demandes[code] = self._demander(env["pays"], env["equipe"],
                                            self._local(1_000_000, self.pays[code]), motif, dg)
        env = self.enveloppes["TG"]
        approuvee = self._demander(env["pays"], env["equipe"],
                                   self._local(500_000, self.pays["TG"]), motif, dg)
        enveloppes.approuver(approuvee, get_access(rh), "Accordé.", Trace.depuis_compte(rh))
        refusee = self._demander(env["pays"], env["equipe"],
                                 self._local(2_000_000, self.pays["TG"]), motif, dg)
        enveloppes.refuser(refusee, get_access(rh),
                           "Refusé : la sous-enveloppe n'est pas consommée.", Trace.depuis_compte(rh))

    def _demander(self, source, cible, montant, motif, user):
        try:
            return enveloppes.demander(source, cible, montant, motif,
                                       get_access(user), Trace.depuis_compte(user)).instance
        except (RegleViolee, PermissionRefusee, HorsPerimetre) as exc:
            raise CommandError(f"Réallocation refusée : {exc}") from exc

    def _calibrer(self):
        """Ramène chaque enveloppe au niveau visé, maintenant que tout est joué.

        Le niveau (`execution_level`) se lit sur la part **consommée** : lignes
        justifiées, non justifiées, clôturées. Une enveloppe sans consommation
        garde son montant.
        """
        for code, env in self.enveloppes.items():
            for budget in env.values():
                budget.refresh_from_db()
                consomme = sum(
                    (e.amount for e in budget.expenses.filter(status__in=CONSUMING_STATUSES)),
                    Decimal("0"),
                )
                part = EN_ALERTE.get(code) or EN_DEPASSEMENT.get(code)
                if part and consomme:
                    budget.amount = (consomme / part).quantize(Decimal("1"))
                    budget.save(update_fields=["amount", "updated_at"])
        # Mali : l'enveloppe de l'équipe 2 laisse passer ce qui est déjà
        # engagé, pas le brouillon du manager — sa soumission sera refusée.
        budget = self.enveloppes[BLOQUE]["pays"]
        brouillon = Dossier.objects.get(number=f"R-{BLOQUE}-01")
        total = sum((e.amount for e in brouillon.expenses.all()), Decimal("0"))
        budget.amount = committed_total(budget) + (total / 2).quantize(Decimal("1"))
        budget.save(update_fields=["amount", "updated_at"])

    # -- Rapport ---------------------------------------------------------------

    def _rapport(self):
        lignes = [
            "# Recette JUSTI INNOV — comptes (fichier local, jamais versionné)",
            "",
            f"Mot de passe de **tous** les comptes : `{self.mot_de_passe}`",
            "",
            "| Compte | Rôle | Périmètre |",
            "|---|---|---|",
        ]
        for suffixe, (role, codes, libelle) in SIEGE.items():
            lignes.append(f"| `{PREFIXE}.{suffixe}` | {role} | {libelle}"
                          f"{' : ' + ', '.join(codes) if codes else ''} |")
        for code, (nom, *_reste) in PAYS.items():
            cc = code.lower()
            lignes.append(f"| `{PREFIXE}.{cc}.manager` | manager | {nom}, tout le pays |")
            lignes.append(f"| `{PREFIXE}.{cc}.equipe` | manager | {nom}, "
                          f"{self.equipes[code][0].name} seulement |")
        lignes += ["", "Guide : `docs/recette.md`. Tout retirer : `docker compose down -v`.", ""]
        try:
            FICHIER.write_text("\n".join(lignes), encoding="utf-8")
            ecrit = f"Comptes écrits dans {FICHIER.name} (ignoré par git)."
        except OSError:
            ecrit = "Fichier des comptes non écrit : notez le mot de passe ci-dessous."
        self.stdout.write(self.style.SUCCESS(
            f"Jeu de recette créé : {len(PAYS)} pays, {len(self.comptes)} comptes, "
            f"{Dossier.objects.filter(number__startswith='R-').count()} dossiers."
        ))
        self.stdout.write(f"Mot de passe de tous les comptes {PREFIXE}.* : {self.mot_de_passe}")
        self.stdout.write(ecrit)
