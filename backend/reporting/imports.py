"""Import d'un classeur Excel de dépenses.

Deux classeurs sont lus par le même code :

- **l'export de la plateforme** (13 colonnes, en-tête en première ligne) ;
- **le classeur historique du client** (« BASE DE DONNEES ACTIONS » : un
  titre fusionné, une note, puis l'en-tête en septième ligne et 9 colonnes —
  N°ORDRE, DATE, TEAM, OWNER, LIBELLE DES TRANSACTIONS, DEPENSES, MONTANT
  JUSTIFIER, ECART, PIECES JUSTIFICATIVES). Ce fichier est mono-pays : le
  pays vient alors de la requête, pas du classeur.

Tout ce qui entre par ici arrive en brouillon, sans montant justifié : le
classeur déclare, le siège constate. MONTANT JUSTIFIER et ECART sont donc
ignorés ; la mention de la pièce (« Reçu », « Reçu(justif incomplet) ») est
conservée en remarque de la ligne, comme une information — pas comme une
preuve. Chaque ligne est validée séparément et signalée par son numéro de
ligne dans le classeur ; rien n'est écrit tant qu'une seule ligne est en
erreur.
"""

import hashlib
import logging
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from openpyxl import load_workbook

from accounts.permissions import get_access, roles_pour
from budget.aggregates import convert
from core.journal import tracer
from core.models import Country, Manager, Team
from expenses.models import AuditLog, Dossier, Expense
from expenses.numerotation import refus_d_ouverture
from expenses.workflow import Status, agit_en_auteur

from .scope import fuseau_de

logger = logging.getLogger(__name__)

# openpyxl lit le XML du classeur avec ``defusedxml`` dès que le paquet est
# installé, ce qui neutralise les entités externes et les « billion laughs »
# qu'un classeur forgé pourrait contenir. L'import est protégé : le code
# fonctionne sans, mais le dit, pour que l'absence se voie dans les journaux
# plutôt qu'au premier classeur malveillant.
try:
    import defusedxml  # noqa: F401

    DEFUSEDXML_DISPONIBLE = True
except ImportError:  # pragma: no cover - dépend de l'environnement
    DEFUSEDXML_DISPONIBLE = False
    logger.warning(
        "defusedxml n'est pas installé : les classeurs importés sont lus "
        "sans protection contre les entités XML."
    )

#: Colonnes sans lesquelles une ligne ne se déclare pas. Ce sont celles du
#: classeur historique : l'export de la plateforme les porte aussi.
COLONNES_OBLIGATOIRES = [
    "N°ORDRE", "DATE", "TEAM", "OWNER", "LIBELLE DES TRANSACTIONS", "DEPENSES",
]

#: Colonnes lues quand elles existent. PAYS manque au classeur historique
#: (mono-pays) ; la devise d'origine n'y figure pas non plus. MONTANT
#: JUSTIFIER, ECART et STATUT ne sont pas lus du tout : le siège constate.
COLONNES_FACULTATIVES = [
    "PAYS", "DEVISE D'ORIGINE", "MONTANT D'ORIGINE", "PIECES JUSTIFICATIVES",
]

#: Deux colonnes dont la présence signe la ligne d'en-tête : elles figurent
#: dans les deux formats et dans aucun titre ni aucune note.
MARQUEURS_D_ENTETE = ("N°ORDRE", "DEPENSES")

#: Lignes parcourues à la recherche de l'en-tête. Le classeur historique le
#: place en septième ligne ; au-delà de quinze, ce n'est plus un titre mais
#: un autre fichier.
LIGNES_D_ENTETE_MAX = 15

#: Nombre maximal de lignes par classeur. Au-delà, ce n'est plus une saisie
#: mais une reprise de données, qui ne doit pas passer par une requête web.
LIGNES_MAX = int(getattr(settings, "IMPORT_MAX_ROWS", 5000))

#: Taille des lots d'insertion : assez grand pour limiter les allers-retours,
#: assez petit pour que la requête reste raisonnable.
TAILLE_LOT = 500

#: Longueurs des champs texte, reprises du modèle : une valeur trop longue
#: doit être refusée ligne par ligne, pas par une erreur de base au moment
#: de l'écriture, qui perdrait tout le classeur.
LONGUEURS = {
    "N°ORDRE": Dossier._meta.get_field("number").max_length,
    "LIBELLE DES TRANSACTIONS": Expense._meta.get_field("title").max_length,
    "DEVISE D'ORIGINE": Expense._meta.get_field("original_currency").max_length,
    "TEAM": Team._meta.get_field("name").max_length,
    "OWNER": Manager._meta.get_field("name").max_length,
}

#: Chiffres avant la virgule autorisés par ``DecimalField(16, 2)``.
CHIFFRES_ENTIERS_MAX = (
    Expense._meta.get_field("amount").max_digits
    - Expense._meta.get_field("amount").decimal_places
)
CENTS = Decimal("0.01")

#: Formats de date acceptés en texte : l'export écrit l'heure, le classeur
#: historique n'en a pas.
FORMATS_DE_DATE = ("%d/%m/%Y %H:%M", "%d/%m/%Y")


def _texte(value):
    return "" if value is None else str(value).strip()


def _texte_borne(row, entete):
    valeur = _texte(row[entete])
    if len(valeur) > LONGUEURS[entete]:
        raise ValueError(
            _("%(entete)s trop long (%(taille)s caractères, maximum %(max)s).")
            % {"entete": entete, "taille": len(valeur), "max": LONGUEURS[entete]}
        )
    return valeur


def _numero_d_ordre(row):
    """Le N°ORDRE en texte, tel qu'un humain l'écrirait.

    Le classeur historique le porte en nombre entier ; une cellule numérique
    relue en flottant donnerait « 12.0 », qui ne rejoindrait jamais le
    dossier « 12 » créé à la main.
    """
    valeur = row["N°ORDRE"]
    if isinstance(valeur, float) and valeur.is_integer():
        valeur = int(valeur)
    if isinstance(valeur, int) and not isinstance(valeur, bool):
        valeur = str(valeur)
    numero = _texte(valeur)
    if len(numero) > LONGUEURS["N°ORDRE"]:
        raise ValueError(
            _("%(entete)s trop long (%(taille)s caractères, maximum %(max)s).")
            % {"entete": "N°ORDRE", "taille": len(numero), "max": LONGUEURS["N°ORDRE"]}
        )
    if not numero:
        raise ValueError(_("N°ORDRE obligatoire."))
    return numero


def _montant(value, entete):
    """Montant positif et fini, ou ``None`` si la cellule est vide.

    ``Decimal`` accepte « NaN » et « Infinity » sans broncher ; la base, non.
    Une telle valeur — ou un montant de plus de quatorze chiffres — doit
    devenir une erreur de ligne, jamais une erreur 500 à l'écriture.
    """
    if value in (None, ""):
        return None
    try:
        montant = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, AttributeError, ValueError):
        raise ValueError(_("%(entete)s illisible : « %(value)s »") % {"entete": entete, "value": value})
    if not montant.is_finite() or montant < 0:
        raise ValueError(_("%(entete)s illisible : « %(value)s »") % {"entete": entete, "value": value})
    montant = montant.quantize(CENTS)
    if montant.adjusted() + 1 > CHIFFRES_ENTIERS_MAX:
        raise ValueError(
            _("%(entete)s trop grand : « %(value)s » (maximum %(max)s chiffres avant la virgule).")
            % {"entete": entete, "value": value, "max": CHIFFRES_ENTIERS_MAX}
        )
    return montant


def _date(value, fuseau):
    """Date de la ligne, avec ou sans heure, dans le fuseau du pays.

    Le classeur historique ne porte que le jour : la dépense est alors datée
    de minuit. Le classeur est écrit à l'heure du pays — c'est celle qu'on
    lit sur les pièces et celle de l'export — et se relit dans ce même
    fuseau : la faire passer par celui du serveur décalait une ligne du
    1er janvier à 01:00 dans l'exercice précédent.
    """
    if isinstance(value, datetime):
        return value.replace(tzinfo=fuseau) if timezone.is_naive(value) else value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=fuseau)
    texte = _texte(value)
    for format_ in FORMATS_DE_DATE:
        try:
            return datetime.strptime(texte, format_).replace(tzinfo=fuseau)
        except ValueError:
            continue
    raise ValueError(_("Date illisible : « %(value)s »") % {"value": value})


def _ouvrir(uploaded):
    taille = getattr(uploaded, "size", None)
    if taille is not None and taille > settings.MAX_PROOF_SIZE:
        limite = settings.MAX_PROOF_SIZE // (1024 * 1024)
        raise ValueError(_("Classeur trop volumineux (maximum %(limite)s Mo).") % {"limite": limite})
    # Un xlsx est une archive : quelques Mo compressés peuvent en cacher
    # des Go de chaînes partagées, qu'openpyxl chargerait en mémoire.
    limite = 5 * settings.MAX_PROOF_SIZE
    try:
        with zipfile.ZipFile(uploaded) as archive:
            decompresse = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile as exc:
        raise ValueError(_("Classeur illisible : ce n'est pas un fichier xlsx.")) from exc
    uploaded.seek(0)
    if decompresse > limite:
        raise ValueError(
            _("Classeur trop volumineux une fois décompressé (maximum %(limite)s Mo).")
            % {"limite": limite // (1024 * 1024)}
        )
    try:
        return load_workbook(uploaded, read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(_("Classeur illisible : %(erreur)s") % {"erreur": exc}) from exc


def _entete(value):
    """Libellé de colonne normalisé : espaces repliés, casse ignorée."""
    return re.sub(r"\s+", " ", _texte(value)).upper()


def _trouver_l_entete(rows):
    """Cherche la ligne d'en-tête dans les premières lignes du classeur.

    Renvoie ``(numéro de ligne, positions des colonnes)``. L'export met
    l'en-tête en première ligne ; le classeur historique l'a en septième,
    sous un titre fusionné et une note. Reconnaître l'en-tête à son contenu
    plutôt qu'à sa place permet de lire les deux — et un classeur remanié.
    """
    for numero, row in enumerate(rows, start=1):
        if numero > LIGNES_D_ENTETE_MAX:
            break
        entetes = [_entete(value) for value in row]
        if all(marqueur in entetes for marqueur in MARQUEURS_D_ENTETE):
            positions = {
                colonne: entetes.index(colonne)
                for colonne in COLONNES_OBLIGATOIRES + COLONNES_FACULTATIVES
                if colonne in entetes
            }
            manquantes = [c for c in COLONNES_OBLIGATOIRES if c not in positions]
            if manquantes:
                raise ValueError(
                    _("En-têtes manquants : %(colonnes)s") % {"colonnes": ", ".join(manquantes)}
                )
            return numero, positions
    raise ValueError(
        _(
            "Ligne d'en-tête introuvable : le classeur doit porter les colonnes "
            "%(colonnes)s dans ses %(max)s premières lignes."
        ) % {"colonnes": ", ".join(COLONNES_OBLIGATOIRES), "max": LIGNES_D_ENTETE_MAX}
    )


def _charger_lignes(uploaded):
    """Lit le classeur et renvoie ``(lignes, colonnes présentes)``.

    Chaque ligne est ``(numéro dans le classeur, {colonne: valeur})`` : le
    numéro est celui qu'Excel affiche, pour que l'erreur signalée se
    retrouve dans le fichier.
    """
    workbook = _ouvrir(uploaded)
    sheet = (
        workbook["BASE DE DONNEES ACTIONS"]
        if "BASE DE DONNEES ACTIONS" in workbook.sheetnames
        else workbook.active
    )
    rows = sheet.iter_rows(values_only=True)
    ligne_d_entete, positions = _trouver_l_entete(rows)

    def cellule(row, colonne):
        position = positions.get(colonne)
        return row[position] if position is not None and position < len(row) else None

    lignes = []
    for line_number, row in enumerate(rows, start=ligne_d_entete + 1):
        if not any(value not in (None, "") for value in row):
            continue
        if (
            _texte(cellule(row, "N°ORDRE")) == ""
            and _texte(cellule(row, "LIBELLE DES TRANSACTIONS")).upper() == "TOTAL"
        ):
            continue
        if len(lignes) >= LIGNES_MAX:
            raise ValueError(
                _("Le classeur dépasse %(max)s lignes : scindez-le.") % {"max": LIGNES_MAX}
            )
        lignes.append(
            (
                line_number,
                {
                    colonne: cellule(row, colonne)
                    for colonne in COLONNES_OBLIGATOIRES + COLONNES_FACULTATIVES
                },
            )
        )
    return lignes, set(positions)


def _erreur(ligne, motif):
    return {"ligne": ligne, "motif": motif}


def _managers_par_pays():
    """Managers actifs, indexés par (pays, nom).

    Un manager n'existe que rattaché à un pays : résoudre « Kodjo Mensah » par
    son seul nom rattachait la ligne au premier homonyme trouvé, fût-il chez
    le voisin.
    """
    index = {}
    for manager in Manager.objects.filter(is_active=True).prefetch_related("countries"):
        for country in manager.countries.all():
            index.setdefault((country.pk, manager.name.casefold()), manager)
    return index


def _devise_d_origine(row, country, date, amount):
    """Applique la règle « les deux ou aucun » du §5.3 et fige le taux.

    Renvoie ``(amount, original_currency, original_amount, original_rate)``.
    Quand la pièce est libellée dans une autre devise, c'est la conversion —
    au taux du jour de la dépense — qui pèse sur l'enveloppe : DEPENSES est
    alors recalculée plutôt que reprise du classeur, pour que la ligne
    importée obéisse à la même règle qu'une ligne saisie.
    """
    devise = _texte_borne(row, "DEVISE D'ORIGINE").upper()
    montant = _montant(row["MONTANT D'ORIGINE"], "MONTANT D'ORIGINE")
    if not devise and montant is None:
        if amount is None:
            raise ValueError(_("Montant de dépense obligatoire."))
        return amount, "", None, None
    if not devise or montant is None:
        raise ValueError(
            _("Indiquez à la fois la devise et le montant d'origine, ou aucun des deux.")
        )
    if devise == country.currency:
        return montant, "", None, None
    converti, taux = convert(montant, devise, country.currency, date.date())
    if converti is None:
        raise ValueError(
            _("Aucun taux connu pour convertir %(devise)s en %(cible)s au %(date)s.")
            % {"devise": devise, "cible": country.currency, "date": date.date().strftime("%d/%m/%Y")}
        )
    return converti, devise, montant, taux


def _note(row):
    """La mention de pièce du classeur, gardée comme information.

    « Reçu » ou « Reçu(justif incomplet) » dans le fichier historique ne
    prouve rien : la pièce elle-même n'est pas dans le classeur. La mention
    est conservée en remarque pour que le contrôleur sache qu'une pièce
    existait au moment de la saisie, et la réclame.
    """
    piece = _texte(row["PIECES JUSTIFICATIVES"])
    return f"Pièce : {piece}" if piece else ""


def _empreinte(number, jour, title, amount):
    """Ce qui fait qu'une ligne « existe déjà » : dossier, jour, libellé, montant.

    Le jour, pas l'instant : le classeur ne porte que la date, alors qu'une
    ligne saisie dans l'application porte l'heure. Comparer les instants
    faisait recréer, à chaque réimport d'un export, toute ligne saisie
    ailleurs qu'à minuit.
    """
    return (number, jour, title, amount)


def cle_d_import(jour, title, amount, number=""):
    """Identité d'une ligne importée dans son dossier (``Expense.import_key``).

    La même chose que :func:`_empreinte`, sans le dossier — qui est l'autre
    colonne de la contrainte —, résumée en une empreinte de taille fixe.
    La validation la compare aux lignes déjà en base ; la base la compare
    à ce que la validation ne peut pas voir, l'autre import en cours.
    Depuis la 2.0, tout un classeur se verse dans un seul dossier
    prédéfini (décision 106) : le N°ORDRE du classeur entre dans
    l'identité, pour ne pas confondre deux lignes identiques de deux
    opérations différentes.
    """
    texte = f"{jour.isoformat()}|{title}|{Decimal(amount):.2f}"
    if number:
        texte = f"{number}|{texte}"
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _lignes_en_base(dossier, cache, number):
    """Ce qui identifie les lignes déjà présentes dans le dossier, lu une fois.

    Deux ensembles : les clés d'import des lignes venues d'un classeur
    (``import_key``, N°ORDRE compris), et les empreintes ``(jour, libellé,
    montant)`` de toutes ses lignes — un classeur exporté de ce dossier
    porte son numéro en N°ORDRE, et ses lignes saisies à la main n'ont pas
    de clé d'import.
    """
    if dossier.pk not in cache:
        fuseau = fuseau_de(dossier.country)
        lignes = list(dossier.expenses.values_list("date", "title", "amount", "import_key"))
        cache[dossier.pk] = (
            {cle for *_reste, cle in lignes if cle},
            {
                (timezone.localtime(instant, fuseau).date(), title, amount)
                for instant, title, amount, _cle in lignes
            },
        )
    return cache[dossier.pk]


def _deja_dans_le_dossier(dossier, cache, number, jour, title, amount):
    """La ligne du classeur est-elle déjà dans le dossier ?"""
    cles, empreintes = _lignes_en_base(dossier, cache, number)
    if cle_d_import(jour, title, amount, number) in cles:
        return True
    return number in (dossier.number, dossier.external_ref) and (jour, title, amount) in empreintes


def _lignes_hors_du_projet(country, project, number, cache):
    """Empreintes des lignes que le même N°ORDRE porte **ailleurs** dans le pays.

    Un classeur se rattache à un projet, mais ses lignes existent peut-être
    déjà dans un dossier d'un autre projet du pays — le même classeur
    importé deux fois dans deux projets, ou un classeur d'avant la 2.0 dont
    les dossiers sont rangés sous « Historique ». Les réimporter
    consommerait deux fois l'enveloppe. Le dossier se désigne par son
    numéro ou sa référence d'origine, comme dans le projet visé.
    """
    cle = (country.pk, project.pk, number)
    if cle not in cache:
        fuseau = fuseau_de(country)
        ailleurs = Expense.objects.filter(dossier__country=country).exclude(
            dossier__project=project
        )
        lignes = ailleurs.filter(Q(dossier__external_ref=number) | Q(dossier__number=number))
        cache[cle] = {
            _empreinte(number, timezone.localtime(instant, fuseau).date(), title, amount)
            for instant, title, amount in lignes.values_list("date", "title", "amount")
        }
        # Depuis la 2.0, un classeur se verse dans un dossier prédéfini : le
        # N°ORDRE n'est plus celui d'un dossier, il vit dans la clé
        # d'import de chaque ligne (décision 106).
        if ("cles", country.pk, project.pk) not in cache:
            cache[("cles", country.pk, project.pk)] = set(
                ailleurs.exclude(import_key=None).values_list("import_key", flat=True)
            )
    return cache[cle]


def _cle_hors_du_projet(country, project, cache, jour, title, amount, number):
    """La clé d'import de la ligne existe-t-elle dans un autre projet du pays ?"""
    return cle_d_import(jour, title, amount, number) in cache.get(
        ("cles", country.pk, project.pk), set()
    )


def _resoudre_le_pays(row, avec_colonne_pays, pays_par_nom, pays_impose, access):
    """Le pays de la ligne : la colonne PAYS, à défaut celui de la requête."""
    pays_nom = _texte(row["PAYS"]) if avec_colonne_pays else ""
    if not pays_nom:
        if pays_impose is None:
            raise ValueError(_("Pays obligatoire : la colonne PAYS est vide."))
        return pays_impose
    country = pays_par_nom.get(pays_nom.casefold())
    if country is None:
        raise ValueError(_("Pays « %(pays)s » inconnu") % {"pays": pays_nom})
    if not access.has_global_scope and country.pk not in access.country_ids:
        raise ValueError(_("Pays « %(pays)s » hors périmètre") % {"pays": country.name})
    return country


def importer_depenses(uploaded, user, dry_run=False, country=None, project=None, kind=None):
    """Valide tout le classeur, puis le crée atomiquement si demandé.

    Depuis la 2.0, un classeur s'importe **dans un projet**, sous un **type
    de dossier** : ``project`` et ``kind``, déjà vérifiés contre le
    périmètre par la vue, sont obligatoires. Ses lignes se versent dans le
    **dossier prédéfini** de ce type (décision 106) — l'import n'ouvre plus
    de dossier —, qui doit être un brouillon de l'importateur. Le N°ORDRE
    du classeur entre dans l'identité de chaque ligne (``import_key``) :
    réimporter le classeur ne recrée rien.

    Le pays est celui du projet. ``country``, s'il est donné, doit être le
    même ; une cellule PAYS d'une autre filiale est refusée.
    """
    try:
        lignes, colonnes = _charger_lignes(uploaded)
    except ValueError as exc:
        return _resultat(0, [_erreur(1, str(exc))], dry_run)

    refus = refus_d_ouverture(project, kind)
    if refus is None and country is not None and country.pk != project.country_id:
        refus = ("project", _("Ce projet appartient à un autre pays que celui de l'import."))
    if refus is not None:
        return _resultat(0, [_erreur(1, refus[1])], dry_run)
    country = project.country
    cible = (
        Dossier.objects.select_related("team", "country")
        .filter(project=project, kind=kind).first()
    )
    if cible is None:
        return _resultat(0, [_erreur(1, _(
            "Ce projet n'a pas de dossier « %(kind)s » : il a été créé avant "
            "ce type de dossier."
        ) % {"kind": kind.name})], dry_run)

    avec_colonne_pays = "PAYS" in colonnes
    if not avec_colonne_pays and country is None:
        return _resultat(
            0,
            [_erreur(1, _(
                "Le classeur n'a pas de colonne PAYS : indiquez le pays "
                "de l'import (paramètre « country »)."
            ))],
            dry_run,
        )

    access = get_access(user)
    # L'import est une déclaration, donc un acte du pays (décision 89) : il
    # obéit aux règles de la saisie. Il ne crée une équipe ou un
    # responsable que pour qui a ce droit sur le référentiel — la RH par
    # défaut, pas le pays — et un manager cloisonné n'importe que pour ses
    # équipes.
    cree_les_equipes = access.role in roles_pour("referentiel.create")
    cree_les_responsables = access.role in roles_pour("managers.create")
    pays = {c.name.casefold(): c for c in Country.objects.all()}
    equipes = {(team.country_id, team.name.casefold()): team for team in Team.objects.all()}
    managers = _managers_par_pays()
    # Équipes et managers que le classeur nomme et que le pays ne connaît
    # pas encore : ils sont créés à l'écriture, une fois par nom. Le
    # classeur historique est la première source du référentiel — exiger
    # qu'il soit saisi à la main avant l'import rendrait l'import inutile.
    equipes_a_creer = {}
    managers_a_creer = {}
    erreurs = []
    valides = []
    # Lignes déjà en base ou déjà vues dans ce classeur : réimporter le même
    # fichier — ou le même classeur collé deux fois — ne doit rien créer.
    empreintes_vues = {}
    lignes_en_base = {}
    lignes_hors_projet = {}

    for numero_ligne, row in lignes:
        try:
            number = _numero_d_ordre(row)
            pays_ligne = _resoudre_le_pays(
                row, avec_colonne_pays, pays, country, access
            )
            if pays_ligne.pk != project.country_id:
                raise ValueError(
                    _("La ligne relève de « %(pays)s », le projet d'un autre pays.")
                    % {"pays": pays_ligne.name}
                )

            date_ligne = _date(row["DATE"], fuseau_de(pays_ligne))
            amount = _montant(row["DEPENSES"], "DEPENSES")
            title = _texte_borne(row, "LIBELLE DES TRANSACTIONS") or "Dépense importée"
            amount, devise, montant_origine, taux = _devise_d_origine(
                row, pays_ligne, date_ligne, amount
            )
            team_name = _texte_borne(row, "TEAM")
            cle_equipe = (pays_ligne.pk, team_name.casefold()) if team_name else None
            team = equipes.get(cle_equipe) if team_name else None
            if team_name and team is None:
                if not cree_les_equipes:
                    raise ValueError(
                        _(
                            "Équipe « %(team)s » inconnue du pays : demandez "
                            "à l'administrateur de la créer."
                        ) % {"team": team_name}
                    )
                equipes_a_creer.setdefault(cle_equipe, (pays_ligne, team_name))
            if access.team_ids is not None and (team is None or team.pk not in access.team_ids):
                raise ValueError(_("La ligne doit porter l'une de vos équipes."))
            owner_name = _texte_borne(row, "OWNER")
            cle_manager = (pays_ligne.pk, owner_name.casefold()) if owner_name else None
            owner = managers.get(cle_manager) if owner_name else None
            if owner_name and owner is None:
                if not cree_les_responsables:
                    raise ValueError(
                        _(
                            "Responsable « %(owner)s » inconnu du pays : "
                            "demandez à l'administrateur de l'inscrire."
                        ) % {"owner": owner_name}
                    )
                managers_a_creer.setdefault(cle_manager, (pays_ligne, owner_name))

            # Toutes les lignes vont au dossier prédéfini du type choisi
            # (décision 106).
            dossier = cible
            cle_dossier = dossier.pk
            if dossier.status != Status.DRAFT:
                raise ValueError(
                    _("Le dossier « %(number)s » est déjà déclaré") % {"number": dossier.number}
                )
            # Un brouillon appartient à son auteur (décision 46) : l'import
            # n'y ajoute pas de lignes au nom d'un collègue.
            if not agit_en_auteur(dossier, access.role, access.username):
                raise ValueError(
                    _("Le dossier « %(number)s » est le brouillon d'un autre compte")
                    % {"number": dossier.number}
                )
            # Le dossier est lu par l'équipe qu'il porte (``ExpenseSerializer``) :
            # une ligne d'une autre équipe y serait visible par la première
            # et invisible pour la seconde.
            if (
                dossier.team_id is not None
                and team_name
                and (team is None or team.pk != dossier.team_id)
            ):
                raise ValueError(
                    _(
                        "Le dossier « %(number)s » porte l'équipe « %(team)s » : "
                        "la ligne doit porter la même."
                    ) % {"number": dossier.number, "team": dossier.team.name}
                )

            empreinte = _empreinte(number, date_ligne.date(), title, amount)
            deja = empreintes_vues.get(empreinte)
            if deja is not None:
                raise ValueError(_("Ligne identique à la ligne %(ligne)s du classeur") % {"ligne": deja})
            if _deja_dans_le_dossier(
                dossier, lignes_en_base, number, date_ligne.date(), title, amount
            ):
                raise ValueError(
                    _(
                        "Ligne déjà présente dans le dossier « %(number)s » : "
                        "même N°ORDRE, même date, même libellé, même montant"
                    ) % {"number": dossier.number}
                )
            if _empreinte(number, date_ligne.date(), title, amount) in _lignes_hors_du_projet(
                pays_ligne, project, number, lignes_hors_projet
            ) or _cle_hors_du_projet(
                pays_ligne, project, lignes_hors_projet, date_ligne.date(), title, amount, number
            ):
                raise ValueError(
                    _(
                        "Ligne déjà présente dans le dossier « %(number)s » d'un autre "
                        "projet du pays : même date, même libellé, même montant"
                    ) % {"number": number}
                )
            empreintes_vues[empreinte] = numero_ligne

            valides.append({
                "ligne": numero_ligne,
                "cle_dossier": cle_dossier,
                "number": number,
                "project": project,
                "kind": kind,
                "country": pays_ligne,
                "team": team,
                "cle_equipe": cle_equipe,
                "owner": owner,
                "cle_manager": cle_manager,
                "date": date_ligne,
                "title": title,
                "amount": amount,
                "original_currency": devise,
                "original_amount": montant_origine,
                "original_rate": taux,
                "note": _note(row),
            })
        except ValueError as exc:
            erreurs.append(_erreur(numero_ligne, str(exc)))

    resultat = _resultat(
        len(valides), erreurs, dry_run,
        equipes_creees=len(equipes_a_creer), managers_crees=len(managers_a_creer),
    )
    if erreurs or dry_run:
        return resultat

    try:
        with transaction.atomic():
            _ecrire(valides, user, equipes, managers, equipes_a_creer, managers_a_creer,
                    cible)
    except _LigneEnErreur as exc:
        # La transaction est défaite : rien n'a été écrit, comme pour une
        # erreur relevée à la validation.
        return _resultat(0, [_erreur(exc.ligne, exc.motif)], dry_run)
    return resultat


class _LigneEnErreur(Exception):
    """Erreur relevée à l'écriture, rapportée à sa ligne du classeur."""

    def __init__(self, ligne, motif):
        super().__init__(motif)
        self.ligne = ligne
        self.motif = motif


def _ecrire(valides, user, equipes, managers, equipes_a_creer, managers_a_creer, cible):
    """Écrit référentiel et lignes, dans la transaction de l'appelant.

    Les lignes vont au dossier prédéfini ``cible``, relu sous verrou.
    """
    # Le référentiel manquant d'abord : les lignes s'y rattachent.
    # ``create`` un par un, et non ``bulk_create`` : la création doit
    # passer par les signaux d'historisation (``ChangeLog``).
    for cle, (pays_equipe, nom) in equipes_a_creer.items():
        equipes[cle] = Team.objects.create(country=pays_equipe, name=nom)
    for cle, (pays_manager, nom) in managers_a_creer.items():
        manager = Manager.objects.create(name=nom)
        pays_manager.managers.add(manager)
        managers[cle] = manager

    depenses = []
    dossier = _verrouiller_le_dossier(cible, valides[0]) if valides else cible
    for ligne in valides:
        if ligne["team"] is None and ligne["cle_equipe"] is not None:
            ligne["team"] = equipes[ligne["cle_equipe"]]
        if ligne["owner"] is None and ligne["cle_manager"] is not None:
            ligne["owner"] = managers[ligne["cle_manager"]]
        depenses.append(
            Expense(
                dossier=dossier,
                country=ligne["country"],
                project=ligne["project"],
                team=ligne["team"],
                owner=ligne["owner"],
                date=ligne["date"],
                title=ligne["title"],
                amount=ligne["amount"],
                # Le classeur peut porter un MONTANT JUSTIFIER : il est
                # ignoré. Une preuve se constate au siège, elle ne
                # s'importe pas.
                justified_amount=Decimal("0.00"),
                original_currency=ligne["original_currency"],
                original_amount=ligne["original_amount"],
                original_rate=ligne["original_rate"],
                note=ligne["note"],
                status=Status.DRAFT,
                created_by=user.username,
                import_key=cle_d_import(
                    ligne["date"].date(), ligne["title"], ligne["amount"], ligne["number"]
                ),
            )
        )
    # Aucun signal n'écoute ``Expense`` : l'insertion par lots ne fait
    # perdre aucune trace, et évite une requête par ligne. La contrainte
    # ``ligne_importee_unique_par_dossier`` tranche ce que la validation n'a
    # pas pu voir : un autre import du même classeur, écrit entre-temps.
    try:
        with transaction.atomic():
            Expense.objects.bulk_create(depenses, batch_size=TAILLE_LOT)
    except IntegrityError:
        raise _LigneEnErreur(
            valides[0]["ligne"],
            _(
                "Un autre import vient d'écrire une ou plusieurs de ces lignes : "
                "relancez l'import, les lignes déjà présentes seront signalées."
            ),
        )


def _verrouiller_le_dossier(dossier, ligne):
    """Relit sous verrou un dossier existant, juste avant d'y écrire.

    Son état a été lu à la validation, sans verrou : soumis entre-temps, il
    recevrait des lignes en brouillon que rien ne soumettrait plus. Le
    verrou fait attendre une soumission en cours, et l'état relu fait foi.
    """
    verrouille = Dossier.objects.select_for_update(of=("self",)).get(pk=dossier.pk)
    if verrouille.status != Status.DRAFT:
        raise _LigneEnErreur(
            ligne["ligne"],
            _("Le dossier « %(number)s » est déjà déclaré") % {"number": dossier.number},
        )
    return verrouille


def _resultat(lignes, erreurs, dry_run, *, equipes_creees=0, managers_crees=0):
    return {
        "lignes_creees": lignes,
        "equipes_creees": equipes_creees,
        "managers_crees": managers_crees,
        "erreurs": erreurs,
        "dry_run": dry_run,
    }


def audit_import(request, resultat, country=None, **contexte):
    """Un import verse des lignes dans le système : il laisse une trace.

    ``country`` est le pays du projet de l'import ; ``contexte`` nomme le
    projet et le type de dossier dans le détail de l'entrée.
    """
    tracer(
        request,
        AuditLog.Action.IMPORTED,
        "ExpenseImport",
        famille="import",
        label="Import des dépenses Excel",
        # Le pays de l'import, quand il vient de la requête : le journal
        # d'un pays doit montrer ce qui y a été versé.
        country=country,
        **contexte,
        **resultat,
    )
