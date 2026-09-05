"""Création des pays et des comptes à partir d'un fichier de description.

Les identifiants ne sont **jamais** écrits dans le dépôt : la commande lit un
fichier local ignoré par git (``seed_users.local.json`` par défaut), dont
``seed_users.example.json`` donne le format.

    python manage.py seed_users --dry-run
    python manage.py seed_users

La commande est faite pour être relancée : elle crée ce qui manque et met à
jour le reste, sans jamais toucher au mot de passe d'un compte existant —
sauf ``reset_password`` explicite — ni re-verrouiller un compte dont le
titulaire a déjà remplacé son mot de passe provisoire.

Chaque compte doit porter une adresse e-mail professionnelle (domaines de
``ALLOWED_EMAIL_DOMAINS``) : la même règle que l'API, appliquée ici parce
que la commande est un chemin d'écriture comme un autre.

Trois clés facultatives complètent le profil et ne sont touchées que si
elles figurent dans le fichier : ``teams`` (noms d'équipes, cherchées dans
les pays du compte), ``manager`` (nom du manager du référentiel que le
compte incarne, ``null`` pour le détacher) et ``language`` (``fr`` ou
``en``).

Une clé ``totp_secret`` (base32) enrôle et confirme d'emblée la double
authentification avec ce secret — que la politique l'exige ou non
(``settings.TOTP_REQUIRED``). Elle n'existe que pour les environnements
jetables — intégration continue, captures d'écran — où un script doit se
connecter sans téléphone : un secret écrit dans un fichier n'est plus un
second facteur. Il n'est jamais affiché.
"""

import base64
import binascii
import json
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Role, UserProfile, aligner_drapeaux
from accounts.validators import valider_email_professionnel
from core.models import Country, Manager, Team
from core.requetes import reset_current_request, set_current_request

DEFAULT_FILE = "seed_users.local.json"

#: Signature des entrées d'historique écrites par la commande : hors requête,
#: le journal ne saurait sinon pas dire *qui* a créé ou modifié un pays.
ACTEUR = "seed_users"


class Command(BaseCommand):
    help = "Crée ou met à jour les pays et les comptes décrits dans un fichier JSON."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default=DEFAULT_FILE,
            help=f"Fichier de description (défaut : {DEFAULT_FILE}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche les opérations sans rien écrire en base.",
        )

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[3] / path
        if not path.exists():
            raise CommandError(
                f"Fichier introuvable : {path}\n"
                "Copiez seed_users.example.json et renseignez-le."
            )

        data = json.loads(path.read_text(encoding="utf-8"))
        dry_run = options["dry_run"]

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
                for payload in data.get("countries", []):
                    self._sync_country(payload)
                for payload in data.get("users", []):
                    self._sync_user(payload)
                if dry_run:
                    raise _Rollback()
        except _Rollback:
            self.stdout.write(self.style.WARNING("\nSimulation : rien n'a été écrit."))
            return
        finally:
            reset_current_request(jeton)

        self.stdout.write(self.style.SUCCESS("\nComptes et pays synchronisés."))

    # -- Pays ---------------------------------------------------------------

    def _sync_country(self, payload):
        ref = payload["country_ref"]
        fields = {
            key: payload[key]
            for key in ("name", "code", "currency", "currency_symbol", "timezone")
            if key in payload
        }
        # Un pays peut préexister sans identifiant fonctionnel (données créées
        # avant l'introduction de `country_ref`) : on l'adopte au lieu de
        # buter sur l'unicité du nom ou du code ISO.
        country = (
            Country.objects.filter(country_ref=ref).first()
            or Country.objects.filter(code=payload["code"]).first()
            or Country.objects.filter(name=payload["name"]).first()
        )
        created = country is None
        if created:
            country = Country()
        country.country_ref = ref
        for key, value in fields.items():
            setattr(country, key, value)
        # ``save()`` n'exécute pas les validateurs de champ : sans
        # ``full_clean()``, le périmètre africain (core/africa.py) n'était
        # vérifié que par l'API, et la commande pouvait créer la France.
        try:
            country.full_clean()
        except ValidationError as exc:
            raise CommandError(
                f"Pays {ref} refusé : "
                + " ; ".join(
                    f"{champ} : {' '.join(messages)}"
                    for champ, messages in exc.message_dict.items()
                )
            ) from exc
        country.save()

        verb = "créé" if created else "mis à jour"
        self.stdout.write(f"Pays {ref:<8} {country.name:<20} {verb}")

    # -- Comptes ------------------------------------------------------------

    def _sync_user(self, payload):
        username = payload["username"]
        role = payload["role"]
        if role not in Role.values:
            raise CommandError(
                f"Rôle inconnu pour {username} : {role!r}. "
                f"Valeurs possibles : {', '.join(Role.values)}"
            )
        refs = payload.get("countries", [])
        if role == Role.MANAGER and not refs:
            # Un manager sans pays ne verrait rien (``has_global_scope``) :
            # le compte serait créé inutilisable, sans que rien ne le dise.
            raise CommandError(
                f"Le manager {username} doit avoir au moins un pays."
            )

        # Vérifiée avant toute écriture : un compte créé sans adresse ne
        # pourrait pas s'enrôler proprement (le QR est libellé par l'e-mail).
        existant = User.objects.filter(username=username).first()
        try:
            email = valider_email_professionnel(
                payload.get("email") or (existant.email if existant else "")
            )
        except ValidationError as exc:
            raise CommandError(
                f"Compte {username} refusé : " + " ".join(exc.messages)
            ) from exc

        user, created = User.objects.get_or_create(username=username)
        user.first_name = payload.get("first_name", user.first_name)
        user.last_name = payload.get("last_name", user.last_name)
        user.email = email
        # Le back-office Django est réservé au siège.
        aligner_drapeaux(user, role)
        user.is_active = payload.get("is_active", True)

        # Le mot de passe du fichier n'est posé qu'à la création, ou sur
        # demande explicite : relancer la commande ne doit pas écraser un mot
        # de passe que le titulaire a choisi depuis.
        password = payload.get("password")
        mot_de_passe_pose = bool(password) and (created or payload.get("reset_password"))
        if mot_de_passe_pose:
            user.set_password(password)
        user.save()

        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"role": role})
        profile.role = role
        if mot_de_passe_pose or "must_change_password" in payload:
            # Un mot de passe distribué par le siège est provisoire. Mais un
            # compte existant dont le mot de passe n'est pas touché garde son
            # état : le re-verrouiller à chaque relance fermait la plateforme
            # à tout le monde le lendemain d'un simple ajout de compte.
            profile.must_change_password = payload.get("must_change_password", True)
        if "totp_secret" in payload:
            self._enroler(profile, username, payload["totp_secret"])
        if "language" in payload:
            profile.language = self._langue(username, payload["language"])

        countries = []
        if refs:
            countries = list(Country.objects.filter(country_ref__in=refs))
            missing = set(refs) - {c.country_ref for c in countries}
            if missing:
                raise CommandError(
                    f"Pays inconnus pour {username} : {', '.join(sorted(missing))}"
                )
        if "manager" in payload:
            profile.manager = self._manager(username, payload["manager"], countries)
        profile.save()

        if countries:
            profile.countries.set(countries)
        else:
            profile.countries.clear()
        if "teams" in payload:
            profile.teams.set(self._equipes(username, payload["teams"], countries))

        scope = ", ".join(refs) if refs else "siège (tous pays)"
        verb = "créé" if created else "mis à jour"
        detail = " (mot de passe posé)" if mot_de_passe_pose else ""
        if "totp_secret" in payload:
            detail += " (2FA enrôlée par le fichier)"
        self.stdout.write(f"Compte {username:<22} {role:<16} {scope:<22} {verb}{detail}")

    def _langue(self, username, langue):
        codes = [code for code, _ in settings.LANGUAGES]
        if langue not in codes:
            raise CommandError(
                f"Compte {username} : langue inconnue {langue!r}. "
                f"Valeurs possibles : {', '.join(codes)}"
            )
        return langue

    def _equipes(self, username, noms, countries):
        """Équipes du compte, cherchées par nom dans ses pays.

        Le nom d'une équipe n'est unique que dans son pays : hors des pays du
        compte, il ne désigne rien — et une équipe d'un autre pays serait
        de toute façon refusée par l'API.
        """
        noms = list(noms or [])
        if noms and not countries:
            raise CommandError(
                f"Compte {username} : des équipes sans pays n'ont pas de sens."
            )
        equipes = list(Team.objects.filter(country__in=countries, name__in=noms))
        manquantes = set(noms) - {t.name for t in equipes}
        if manquantes:
            raise CommandError(
                f"Équipes inconnues dans les pays de {username} : "
                f"{', '.join(sorted(manquantes))}"
            )
        return equipes

    def _manager(self, username, nom, countries):
        """Manager du référentiel que le compte incarne, ou ``None``.

        Le nom d'un manager n'est pas unique : la recherche se limite aux
        managers rattachés aux pays du compte, et une ambiguïté restante
        est une erreur — le fichier doit être corrigé, pas deviné.
        """
        if nom in (None, ""):
            return None
        candidats = Manager.objects.filter(name=nom)
        if countries:
            candidats = candidats.filter(countries__in=countries).distinct()
        candidats = list(candidats)
        if not candidats:
            raise CommandError(f"Manager inconnu pour {username} : {nom!r}")
        if len(candidats) > 1:
            raise CommandError(
                f"Plusieurs managers portent le nom {nom!r} pour {username} : "
                "précisez-le dans le référentiel avant de relancer."
            )
        return candidats[0]

    def _enroler(self, profile, username, secret):
        """Pose un secret TOTP venu du fichier et le tient pour confirmé.

        Le secret est vérifié (base32 non vide) mais jamais écrit sur la
        sortie : il vaut un mot de passe. Relancée avec le même secret, la
        commande ne change rien ; avec un autre, elle le remplace — le
        fichier fait foi dans un environnement jetable.
        """
        secret = str(secret or "").strip().replace(" ", "").upper()
        try:
            if not secret or not base64.b32decode(secret + "=" * (-len(secret) % 8)):
                raise ValueError
        except (binascii.Error, ValueError):
            raise CommandError(
                f"Compte {username} : totp_secret doit être un secret base32 non vide."
            ) from None
        if profile.totp_secret != secret or profile.totp_confirmed_at is None:
            profile.totp_secret = secret
            profile.totp_confirmed_at = timezone.now()
            # Nouveau secret : la mémoire anti-rejeu repart.
            profile.totp_last_counter = None


class _Rollback(Exception):
    """Annule la transaction en mode simulation."""
