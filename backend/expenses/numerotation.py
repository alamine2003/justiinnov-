"""Numéros calculés des dossiers (décision 102).

Un dossier ouvert dans un projet reçoit le numéro de ce projet suivi de son
rang dans le projet : ``TG-P-2026-001-D001``. Le rang repart de 1 dans
chaque projet ; il ne se saisit pas et ne change plus.

La ligne du projet est verrouillée le temps de lire le dernier rang et
d'enregistrer le dossier : deux dossiers ouverts au même instant dans le
même projet ne tirent pas le même rang. La contrainte
``unique_rang_de_dossier`` reste en garde derrière.
"""

from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

from core.models import Project

from .models import Dossier


def numero_de_dossier(reference_du_projet, rang):
    """``TG-P-2026-001-D001`` : trois chiffres, davantage au-delà de 999."""
    return f"{reference_du_projet}-D{rang:03d}"


def creer_dossier(dossier):
    """Enregistre un dossier neuf avec son rang et son numéro.

    ``dossier`` n'est pas encore en base ; son projet est renseigné et a une
    référence. Rend le dossier enregistré.
    """
    if dossier.pk is not None:
        raise ValueError("Un dossier ne se numérote qu'à sa création.")
    with transaction.atomic():
        # ``no_key`` : le verrou sérialise les numérotations sans bloquer
        # les écritures qui ne font que référencer le projet (une ligne
        # enregistrée par un collègue prend un FOR KEY SHARE sur lui).
        projet = Project.objects.select_for_update(no_key=True).get(pk=dossier.project_id)
        if not projet.reference:
            raise ValueError("Le projet n'a pas de référence : il ne se numérote pas.")
        dernier = (
            Dossier.objects.filter(project=projet)
            .aggregate(dernier=Max("sequence"))["dernier"]
            or 0
        )
        dossier.sequence = dernier + 1
        dossier.number = numero_de_dossier(projet.reference, dossier.sequence)
        dossier.save()
    return dossier


def refus_d_ouverture(projet, kind):
    """Pourquoi un dossier ne s'ouvrirait pas dans ``projet`` sous ``kind``.

    Rend ``(champ, message)``, ou ``None`` si l'ouverture est permise
    (décision 102) : un projet actif et typé, un type de dossier actif et
    de ce type de projet. Seule règle, partagée par la saisie
    (``DossierSerializer``) et l'import (``reporting.imports``).
    """
    if projet is None:
        return "project", _("Choisissez le projet dans lequel ouvrir ce dossier.")
    if not projet.accepte_des_dossiers:
        if projet.is_historical or not projet.kind_id:
            return "project", _("Ce projet n'a pas de type : il n'accepte pas de nouveau dossier.")
        return "project", _("Ce projet est désactivé : il n'accepte plus de dossier.")
    if kind is None:
        return "kind", _("Choisissez le type du dossier : stands, voyages, billets…")
    if not kind.is_active or kind.project_kind_id != projet.kind_id:
        return "kind", _("Ce type de dossier ne s'ouvre pas dans ce projet.")
    return None
