"""La corbeille du super administrateur (décision 120).

Avant la mise en ligne finale, la production porte des saisies d'essai :
des projets, des dossiers, des lignes et des justificatifs que les pays ont
écrits pour éprouver l'outil. Le super administrateur les retire d'ici,
tant que la configuration tient la corbeille ouverte
(``WorkflowConfiguration.suppressions_ouvertes``) ; on la ferme à
l'ouverture aux filiales, et plus rien ne se retire.

Retirer, c'est trois choses, dans une transaction :

- écrire une copie figée de chaque objet dans ``ElementSupprime``, que la
  base refuse de modifier ou de supprimer ;
- retirer l'objet de sa table, avec ce qui en dépend — un projet emporte
  ses dossiers, un dossier ses lignes, une ligne ses justificatifs et ses
  demandes de rectification ; chacun laisse une entrée ``trashed`` au
  journal d'audit ;
- garder le fichier de chaque justificatif dans le stockage : la corbeille
  le cite, il se télécharge encore.

L'objet quitte vraiment sa table : enveloppes, tableaux de bord, exports,
alertes et numérotation se recalculent sans qu'aucune lecture ait à
filtrer un drapeau. Un numéro libéré peut donc resservir — un pays vidé
recommence à ``-001`` ; l'ancien objet reste ici, sous son identifiant.

Un refus est une exception de ``core.regles`` : la vue la traduit.
"""

from dataclasses import dataclass, field

from django.db import transaction
from django.utils.translation import gettext as _

from accounts.perimetre import PAYS_ENTIER
from accounts.permissions import exiger_la_capacite
from budget.models import Budget
from core import journal
from core.models import Project, WorkflowConfiguration
from core.regles import HorsPerimetre, RegleViolee
from notifications import triggers

from .audit import enregistrer, preparer
from .models import AuditLog, Dossier, ElementSupprime, Expense, Proof, Rectification
from .workflow import RECTIFIABLE_STATUSES

Nature = ElementSupprime.Nature
TRASHED = AuditLog.Action.TRASHED

#: Le modèle de chaque nature, pour retrouver l'objet visé.
MODELES = {
    Nature.PROJET: Project,
    Nature.DOSSIER: Dossier,
    Nature.LIGNE: Expense,
    Nature.PIECE: Proof,
}


@dataclass
class Resultat:
    """Ce que rend la mise à la corbeille : l'élément de tête et ce qu'il a emporté."""

    element: ElementSupprime
    emportes: dict = field(default_factory=dict)
    audit: list = field(default_factory=list)


def exiger_la_corbeille_ouverte():
    """Refus si la corbeille est fermée — lu en base, pas en cache.

    Fermée à la mise en ligne finale, elle doit l'être à la requête
    suivante : le cache de la configuration vit jusqu'à une minute.
    """
    configuration = WorkflowConfiguration.objects.filter(pk=1).first()
    if configuration is None or not configuration.suppressions_ouvertes:
        raise RegleViolee(
            "nature",
            _(
                "Les suppressions sont fermées : la corbeille ne s'ouvre que "
                "dans Configuration, par le super administrateur."
            ),
        )


def _photo(instance):
    """Les champs de l'objet, sous la forme du journal."""
    return {
        champ.attname: journal.serialisable(getattr(instance, champ.attname))
        for champ in instance._meta.concrete_fields
    }


class _Retrait:
    """Accumule les copies et les entrées du journal d'une mise à la corbeille."""

    def __init__(self, acteur, motif, trace):
        self.acteur = acteur
        self.motif = motif
        self.trace = trace
        self.racine = None
        self.copies = []
        self.audit = []
        self.emportes = dict.fromkeys(Nature.values, 0)

    def _copie(self, nature, instance, *, reference, libelle, country,
               montant=None, fichier="", sha256="", **en_plus):
        copie = ElementSupprime(
            nature=nature, objet_id=instance.pk,
            reference=(reference or "")[:64], libelle=(libelle or "")[:250],
            country=country, montant=montant,
            devise=country.currency if montant is not None else "",
            donnees={**_photo(instance), **en_plus},
            fichier=fichier, sha256=sha256, motif=self.motif,
            supprime_par=self.acteur.username, ip_address=self.trace.ip,
        )
        if self.racine is None:
            # La tête d'abord : ce qu'elle emporte la cite.
            copie.save()
            self.racine = copie
        else:
            copie.racine = self.racine
            self.copies.append(copie)
        self.emportes[nature] += 1
        self.audit.append(
            preparer(
                self.trace, TRASHED, instance,
                label=f"Mis à la corbeille — {libelle or reference}"[:250],
                country=country, motif=self.motif, nature=nature,
                reference=reference, corbeille=self.racine.pk,
                **({"amount": str(montant)} if montant is not None else {}),
            )
        )
        return copie

    def pieces(self, pieces):
        """Des justificatifs, le plus récent d'abord : une version protège
        celle qu'elle remplace. Leur fichier reste dans le stockage."""
        for piece in pieces.select_related("dossier__country").order_by("-pk"):
            dossier = piece.dossier
            self._copie(
                Nature.PIECE, piece,
                reference=dossier.number, libelle=str(piece),
                country=dossier.country, fichier=piece.file.name, sha256=piece.sha256,
            )
            piece.delete()

    def ligne(self, ligne):
        """Une ligne, avec ses justificatifs et ses demandes de rectification."""
        demandes = list(Rectification.objects.filter(expense=ligne).order_by("-pk"))
        copie = self._copie(
            Nature.LIGNE, ligne,
            reference=ligne.dossier.number, libelle=ligne.title,
            country=ligne.country, montant=ligne.amount,
            rectifications=[_photo(demande) for demande in demandes],
        )
        self.pieces(ligne.proofs.select_for_update(of=("self",)))
        # Les demandes de rectification protègent la ligne en base ; elles
        # partent dans sa copie.
        for demande in demandes:
            self.audit.append(
                preparer(
                    self.trace, TRASHED, demande,
                    label=f"Mis à la corbeille avec sa ligne — {demande}"[:250],
                    country=ligne.country, motif=self.motif,
                    expense_id=ligne.pk, corbeille=self.racine.pk,
                )
            )
            demande.delete()
        ligne.delete()
        return copie

    def dossier(self, dossier):
        """Un dossier, ses lignes, et les pièces d'avant la 2.0 rangées sur lui."""
        lignes = list(
            dossier.expenses.select_for_update(of=("self",))
            .select_related("country", "dossier").order_by("pk")
        )
        self._copie(
            Nature.DOSSIER, dossier,
            reference=dossier.number, libelle=dossier.label,
            country=dossier.country, lines=len(lignes),
        )
        for ligne in lignes:
            self.ligne(ligne)
        self.pieces(dossier.proofs.select_for_update(of=("self",)))
        dossier.delete()

    def projet(self, projet):
        dossiers = list(
            projet.dossiers.select_for_update(of=("self",))
            .select_related("country").order_by("pk")
        )
        self._copie(
            Nature.PROJET, projet,
            reference=projet.reference or "", libelle=projet.name,
            country=projet.country, dossiers=len(dossiers),
        )
        for dossier in dossiers:
            self.dossier(dossier)
        # Le signal de l'historique du référentiel trace aussi sa suppression.
        projet.delete()

    def terminer(self):
        ElementSupprime.objects.bulk_create(self.copies)
        enregistrer(self.audit)


def _exiger_le_perimetre(acteur, country_id):
    if not acteur.has_global_scope and country_id not in acteur.country_ids:
        raise HorsPerimetre()


def _chaine(piece):
    """Toutes les versions d'un justificatif, de la plus ancienne à la plus récente."""
    premiere = piece
    while premiere.replaces_id:
        premiere = Proof.objects.get(pk=premiere.replaces_id)
    versions = [premiere]
    suivante = Proof.objects.filter(replaces=premiere).first()
    while suivante is not None:
        versions.append(suivante)
        suivante = Proof.objects.filter(replaces=suivante).first()
    return versions


def _verrouiller(nature, pk):
    """L'objet visé, sous verrou — son dossier d'abord, comme les autres services."""
    modele = MODELES[nature]
    if nature in (Nature.LIGNE, Nature.PIECE):
        dossier_id = modele.objects.filter(pk=pk).values_list("dossier_id", flat=True).first()
        if dossier_id is None:
            raise modele.DoesNotExist
        Dossier.objects.select_for_update().filter(pk=dossier_id).first()
    relations = ("dossier__country",) if nature == Nature.PIECE else ("country",)
    return modele.objects.select_for_update(of=("self",)).select_related(*relations).get(pk=pk)


@transaction.atomic
def mettre_a_la_corbeille(nature, pk, acteur, motif, trace):
    """Met un projet, un dossier, une ligne ou un justificatif à la corbeille.

    Refusée si la corbeille est fermée, sans motif, au-delà du périmètre ;
    pour le projet « Historique » (né d'une migration, pas d'un pays) ; pour
    un projet qui porte une enveloppe (qui le protège en base) ; pour la
    pièce d'une ligne constatée, qui resterait justifiée sans preuve — c'est
    alors la ligne qui part.
    """
    exiger_la_capacite("corbeille.supprimer", acteur)
    exiger_la_corbeille_ouverte()
    motif = (motif or "").strip()
    if not motif:
        raise RegleViolee("motif", _("Le motif est obligatoire."))
    if nature not in MODELES:
        raise RegleViolee("nature", _("Nature inconnue."))
    try:
        objet = _verrouiller(nature, pk)
    except MODELES[nature].DoesNotExist:
        raise HorsPerimetre() from None

    retrait = _Retrait(acteur, motif, trace)
    team = PAYS_ENTIER
    if nature == Nature.PROJET:
        _exiger_le_perimetre(acteur, objet.country_id)
        if objet.is_historical:
            raise RegleViolee(
                "nature",
                _("Le projet « Historique » range les dossiers d'avant la 2.0 : il ne se retire pas."),
            )
        if Budget.objects.filter(project=objet).exists():
            raise RegleViolee(
                "nature",
                _(
                    "Ce projet porte une enveloppe : supprimez-la ou rattachez-la "
                    "ailleurs avant de mettre le projet à la corbeille."
                ),
            )
        retrait.projet(objet)
    elif nature == Nature.DOSSIER:
        _exiger_le_perimetre(acteur, objet.country_id)
        team = objet.team
        retrait.dossier(objet)
    elif nature == Nature.LIGNE:
        _exiger_le_perimetre(acteur, objet.country_id)
        team = objet.team
        retrait.ligne(objet)
    else:
        dossier = objet.dossier
        _exiger_le_perimetre(acteur, dossier.country_id)
        # Une pièce d'avant la 2.0, sans ligne, prouve le dossier entier.
        statut = objet.expense.status if objet.expense_id else dossier.status
        if statut in RECTIFIABLE_STATUSES:
            raise RegleViolee(
                "nature",
                _(
                    "Cette pièce prouve une ligne déjà constatée : elle ne part pas "
                    "seule. Mettez la ligne à la corbeille si elle doit partir."
                ),
            )
        team = dossier.team
        versions = [p.pk for p in _chaine(objet)]
        retrait.pieces(Proof.objects.filter(pk__in=versions).select_for_update(of=("self",)))

    retrait.terminer()
    triggers.mis_a_la_corbeille(retrait.racine, team, trace.compte)
    return Resultat(retrait.racine, emportes=retrait.emportes, audit=retrait.audit)
