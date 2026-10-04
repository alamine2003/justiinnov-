"""Les dossiers prédéfinis d'un projet (décision 106).

Un projet naît avec ses dossiers : un par type actif de la liste commune
(``DossierKind``) pour son type de projet — Stands, T-shirts, Collations,
Voyages pour un congrès ; Billets, Carburant, Hôtellerie, Repas, Forfait
pour un voyage ; Soutien financier. Le pays ne crée ni ne supprime de
dossier : il saisit ses lignes dans ceux-là. Chaque dossier est numéroté
dans son projet (``expenses.numerotation``) et tracé.

Un type ajouté plus tard à la liste vaut pour les projets créés ensuite :
les projets existants ne sont pas complétés d'office ; le siège complète
un projet à la demande (``POST /api/projects/{id}/completer/``).
"""

from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from core.models import DossierKind, Project

from .audit import record
from .models import AuditLog, Dossier
from .numerotation import creer_dossier
from .workflow import Status


#: Valeur d'``equipe`` qui reprend celle des dossiers déjà ouverts.
EQUIPE_DU_PROJET = object()


def _equipe_commune(projet):
    """L'équipe que portent tous les dossiers prédéfinis du projet, ou ``None``.

    Un projet complété après coup (``completer``) doit rester lisible par
    l'équipe qui le tient : un dossier ajouté sans équipe échappait au
    manager rattaché à cette équipe, qui ne voyait plus que les anciens.
    Plusieurs équipes, ou aucune : rien ne se devine, ``None``.
    """
    equipes = set(
        projet.dossiers.filter(predefini=True).values_list("team_id", flat=True)
    )
    if len(equipes) != 1:
        return None
    (equipe,) = equipes
    return equipe


def creer_les_dossiers_predefinis(projet, *, auteur="", equipe=None, trace):
    """Ouvre dans ``projet`` un dossier par type actif de son type de projet.

    ``auteur`` signe les brouillons (``created_by``) : le manager qui crée
    le projet en est l'auteur, et lui seul les soumet (décision 46). Vide
    quand le siège type un projet d'avant la 2.0 : les dossiers reviennent
    alors au pays, et le premier qui soumet en devient l'auteur.
    ``equipe`` va sur chaque dossier, donc sur chaque ligne : un manager
    rattaché à des équipes les voit (cloisonnement par équipe).
    :data:`EQUIPE_DU_PROJET` reprend l'équipe commune des dossiers
    prédéfinis déjà là (:func:`_equipe_commune`), lue sous le verrou du
    projet. Rend les dossiers créés, dans l'ordre de la liste commune.
    """
    if not projet.accepte_des_dossiers:
        return []
    jour = timezone.localtime(timezone.now(), ZoneInfo(projet.country.timezone)).date()
    crees = []
    with transaction.atomic():
        # Projet verrouillé : deux typages ou deux complétions simultanés
        # ne liraient pas le même « déjà là ».
        Project.objects.select_for_update().filter(pk=projet.pk).first()
        deja = set(projet.dossiers.filter(predefini=True).values_list("kind_id", flat=True))
        equipe_id = (
            _equipe_commune(projet)
            if equipe is EQUIPE_DU_PROJET
            else getattr(equipe, "pk", equipe)
        )
        for kind in DossierKind.objects.filter(
            project_kind=projet.kind, is_active=True
        ).exclude(pk__in=deja):
            dossier = creer_dossier(Dossier(
                project=projet, kind=kind, label=kind.name, country=projet.country,
                team_id=equipe_id, date=jour, status=Status.DRAFT, created_by=auteur,
                predefini=True,
            ))
            record(trace, AuditLog.Action.CREATED, dossier)
            crees.append(dossier)
    return crees
