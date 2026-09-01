"""Création des pays et des comptes à partir d'un fichier de description.

Les identifiants ne sont **jamais** écrits dans le dépôt : la commande lit un
fichier local ignoré par git (``seed_users.local.json`` par défaut), dont
``seed_users.example.json`` donne le format.

    python manage.py seed_users --dry-run
    python manage.py seed_users
"""

import json
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Role, UserProfile
from core.models import Country

DEFAULT_FILE = "seed_users.local.json"


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

        user, created = User.objects.get_or_create(username=username)
        user.first_name = payload.get("first_name", user.first_name)
        user.last_name = payload.get("last_name", user.last_name)
        user.email = payload.get("email", user.email)
        # Le back-office Django est réservé au siège.
        user.is_staff = role in (Role.SUPER_ADMIN, Role.ADMIN)
        user.is_superuser = role == Role.SUPER_ADMIN
        user.is_active = payload.get("is_active", True)

        password = payload.get("password")
        if password and created:
            user.set_password(password)
        elif password and payload.get("reset_password"):
            user.set_password(password)
        user.save()

        profile, _ = UserProfile.objects.update_or_create(
            user=user,
            defaults={
                "role": role,
                # Un mot de passe distribué par le siège est provisoire.
                "must_change_password": payload.get("must_change_password", True),
            },
        )
        refs = payload.get("countries", [])
        if refs:
            countries = list(Country.objects.filter(country_ref__in=refs))
            missing = set(refs) - {c.country_ref for c in countries}
            if missing:
                raise CommandError(
                    f"Pays inconnus pour {username} : {', '.join(sorted(missing))}"
                )
            profile.countries.set(countries)
        else:
            profile.countries.clear()

        scope = ", ".join(refs) if refs else "siège (tous pays)"
        verb = "créé" if created else "mis à jour"
        self.stdout.write(f"Compte {username:<22} {role:<16} {scope:<22} {verb}")


class _Rollback(Exception):
    """Annule la transaction en mode simulation."""
