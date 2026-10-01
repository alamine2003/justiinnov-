"""Références calculées des projets (décision 100).

Un projet reçoit à sa création une référence qui ne changera plus :
``TG-P-2026-001`` — le code de son pays, ``P``, l'année et son rang dans le
pays et l'année. Le rang repart de 1 chaque année, dans chaque pays.

Deux créations simultanées dans le même pays ne doivent pas tirer le même
rang : la ligne du pays est verrouillée (``select_for_update``) le temps de
lire le dernier rang et d'enregistrer le projet. La contrainte
``unique_rang_de_projet`` reste en garde derrière.

Les dossiers se numérotent dans leur projet (``expenses.numerotation``) :
``core`` ne connaît pas les dossiers.
"""

from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import Country, Project


def reference_de_projet(code, annee, rang):
    """``TG-P-2026-001`` : trois chiffres, davantage au-delà de 999."""
    return f"{code}-P-{annee}-{rang:03d}"


def annee_locale(country):
    """L'année en cours dans le fuseau du pays : un projet ouvert à Lomé le
    1er janvier à 00:30 est de la nouvelle année, même s'il est encore le
    31 décembre à Paris."""
    return timezone.localtime(timezone.now(), ZoneInfo(country.timezone)).year


def creer_projet(project):
    """Enregistre un projet neuf avec son année, son rang et sa référence.

    ``project`` n'est pas encore en base ; son pays est renseigné. Rend le
    projet enregistré.
    """
    if project.pk is not None:
        raise ValueError("Un projet ne se numérote qu'à sa création.")
    with transaction.atomic():
        country = Country.objects.select_for_update().get(pk=project.country_id)
        annee = annee_locale(country)
        dernier = (
            Project.objects.filter(country=country, year=annee)
            .aggregate(dernier=Max("sequence"))["dernier"]
            or 0
        )
        project.year = annee
        project.sequence = dernier + 1
        project.reference = reference_de_projet(country.code, annee, project.sequence)
        project.save()
    return project
