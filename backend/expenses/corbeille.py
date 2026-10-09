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
from core.requetes import motif_du_journal
from core.regles import HorsPerimetre, RegleViolee
from notifications import triggers

from .audit import enregistrer, preparer
from .models import AuditLog, Dossier, ElementSupprime, Expense, Proof, Rectification
from .workflow import RECTIFIABLE_STATUSES, Status

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

    def _copie_de_piece(self, piece):
        dossier = piece.dossier
        self._copie(
            Nature.PIECE, piece,
            reference=dossier.number, libelle=str(piece),
            country=dossier.country, fichier=piece.file.name, sha256=piece.sha256,
        )

    def pieces(self, pieces, choisie=None):
        """Des justificatifs, le plus récent d'abord : une version protège
        celle qu'elle remplace. Leur fichier reste dans le stockage.

        ``choisie`` — la version que le super administrateur a visée — est
        copiée la première : elle est la tête que les autres citent.
        """
        if choisie is not None:
            self._copie_de_piece(choisie)
        for piece in pieces.select_related("dossier__country").order_by("-pk"):
            if choisie is None or piece.pk != choisie.pk:
                self._copie_de_piece(piece)
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
        # Le signal de l'historique du référentiel trace aussi sa
        # suppression ; le motif y va comme à toute modification d'un
        # projet (décision 109).
        with motif_du_journal(self.motif):
            projet.delete()

    def terminer(self):
        ElementSupprime.objects.bulk_create(self.copies)
        enregistrer(self.audit)


def _exiger_le_perimetre(acteur, country_id):
    if not acteur.has_global_scope and country_id not in acteur.country_ids:
        raise HorsPerimetre()


def versions_chargees(piece):
    """Les versions d'une pièce, prises dans les pièces de son dossier déjà
    préchargées (fiche d'un dossier) — sans requête ; la pièce seule si
    rien n'est préchargé."""
    chargees = getattr(piece.dossier, "_prefetched_objects_cache", {}).get("proofs")
    if chargees is None:
        return [piece]
    par_id = {p.pk: p for p in chargees}
    suivante = {p.replaces_id: p for p in chargees if p.replaces_id}
    versions = [piece]
    courante = piece
    while courante.replaces_id in par_id:
        courante = par_id[courante.replaces_id]
        versions.append(courante)
    courante = piece
    while courante.pk in suivante:
        courante = suivante[courante.pk]
        versions.append(courante)
    return versions


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


def prouve_un_constat(piece):
    """La pièce prouve-t-elle une ligne justifiée ou clôturée ? Elle ne part
    alors pas seule.

    Une pièce d'avant la 2.0, sans ligne, prouve **toutes** les lignes de son
    dossier (``Dossier.lignes_sans_preuve``) : il suffit que l'une soit
    constatée — les lignes se justifient une à une, avant leur dossier.
    """
    if piece.expense_id:
        return piece.expense.status in RECTIFIABLE_STATUSES
    return piece.dossier.status in RECTIFIABLE_STATUSES or piece.dossier.expenses.filter(
        status__in=RECTIFIABLE_STATUSES
    ).exists()


def _verrouiller(nature, pk):
    """L'objet visé, sous verrou — son dossier d'abord, comme les autres services."""
    modele = MODELES[nature]
    if nature in (Nature.LIGNE, Nature.PIECE):
        dossier_id = modele.objects.filter(pk=pk).values_list("dossier_id", flat=True).first()
        if dossier_id is None:
            raise modele.DoesNotExist
        Dossier.objects.select_for_update().filter(pk=dossier_id).first()
    relations = ("dossier__country",) if nature == Nature.PIECE else ("country",)
    # Le projet sans clé : une saisie concurrente verrouille son dossier
    # puis vérifie, au commit, le projet de sa ligne (``FOR KEY SHARE``) ;
    # un ``FOR UPDATE`` ici les interbloquerait (même choix que
    # ``numerotation``).
    return (
        modele.objects.select_for_update(of=("self",), no_key=nature == Nature.PROJET)
        .select_related(*relations)
        .get(pk=pk)
    )


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
        # Des lignes rangées ailleurs — dans le dossier « Historique » du
        # pays, depuis la 2.0 — peuvent encore citer le projet : elles le
        # protègent en base, et elles ne partent pas avec lui.
        ailleurs = Expense.objects.filter(project=objet).exclude(dossier__project=objet)
        if ailleurs.exists():
            raise RegleViolee(
                "nature",
                _(
                    "{count} ligne(s) d'un autre dossier ({dossier}) citent encore ce "
                    "projet : mettez-les à la corbeille d'abord."
                ).format(count=ailleurs.count(), dossier=ailleurs.first().dossier.number),
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
        # Vidé de sa dernière ligne, un dossier déclaré se justifierait et se
        # clôturerait à vide — et, clôturé, garderait pour toujours la place
        # de son type dans le projet. C'est alors le dossier qui part.
        dossier = objet.dossier
        if dossier.status != Status.DRAFT and not dossier.expenses.exclude(pk=objet.pk).exists():
            raise RegleViolee(
                "nature",
                _(
                    "C'est la dernière ligne d'un dossier déclaré : mettez plutôt "
                    "le dossier {dossier} à la corbeille."
                ).format(dossier=dossier.number),
            )
        team = objet.team
        retrait.ligne(objet)
    else:
        dossier = objet.dossier
        _exiger_le_perimetre(acteur, dossier.country_id)
        # Toutes ses versions partent : aucune ne doit prouver un constat.
        # Une pièce d'avant la 2.0, sans ligne, prouve le dossier entier.
        versions = _chaine(objet)
        if any(prouve_un_constat(version) for version in versions):
            raise RegleViolee(
                "nature",
                _(
                    "Cette pièce prouve une ligne déjà constatée : elle ne part pas "
                    "seule. Mettez la ligne à la corbeille si elle doit partir."
                ),
            )
        team = dossier.team
        retrait.pieces(
            Proof.objects.filter(pk__in=[v.pk for v in versions]).select_for_update(of=("self",)),
            choisie=objet,
        )

    retrait.terminer()
    triggers.mis_a_la_corbeille(retrait.racine, team, trace.compte)
    return Resultat(retrait.racine, emportes=retrait.emportes, audit=retrait.audit)
