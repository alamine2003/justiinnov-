"""Aides partagées par les suites : sources du dépôt, trace d'un compte."""

from pathlib import Path

from core.journal import Trace

#: Racine du backend (le dossier qui contient ``manage.py``).
RACINE = Path(__file__).resolve().parents[2]

#: Adresse d'où agissent les comptes de test.
ADRESSE = "41.79.0.10"


def sources():
    """Modules Python du backend, hors tests, migrations et environnement."""
    for chemin in sorted(RACINE.rglob("*.py")):
        parties = chemin.relative_to(RACINE).parts
        if "tests" in parties or "migrations" in parties or ".venv" in parties:
            continue
        yield chemin


def trace(user):
    """La trace qu'une vue construirait depuis la requête de ``user``."""
    return Trace(user=user.username, ip=ADRESSE, user_agent="Test", compte=user)
