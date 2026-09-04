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

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook

from accounts.permissions import get_access
from budget.aggregates import convert
from core.models import Country, Manager, Team
from core.requetes import client_ip
from expenses.models import AuditLog, Dossier, Expense
from expenses.workflow import Status

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
            f"{entete} trop long ({len(valeur)} caractères, "
            f"maximum {LONGUEURS[entete]})."
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
            f"N°ORDRE trop long ({len(numero)} caractères, "
            f"maximum {LONGUEURS['N°ORDRE']})."
        )
    if not numero:
        raise ValueError("N°ORDRE obligatoire.")
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
        raise ValueError(f"{entete} illisible : « {value} »")
    if not montant.is_finite() or montant < 0:
        raise ValueError(f"{entete} illisible : « {value} »")
    montant = montant.quantize(CENTS)
    if montant.adjusted() + 1 > CHIFFRES_ENTIERS_MAX:
        raise ValueError(
            f"{entete} trop grand : « {value} » "
            f"(maximum {CHIFFRES_ENTIERS_MAX} chiffres avant la virgule)."
        )
    return montant


def _date(value):
    """Date de la ligne, avec ou sans heure.

    Le classeur historique ne porte que le jour : la dépense est alors datée
    de minuit. Le fuseau est celui du serveur ; l'affichage la relit dans
    celui du pays, comme toute autre ligne.
    """
    if isinstance(value, datetime):
        return timezone.make_aware(value) if timezone.is_naive(value) else value
    if isinstance(value, date):
        return timezone.make_aware(datetime.combine(value, datetime.min.time()))
    texte = _texte(value)
    for format_ in FORMATS_DE_DATE:
        try:
            return timezone.make_aware(datetime.strptime(texte, format_))
        except ValueError:
            continue
    raise ValueError(f"Date illisible : « {value} »")


def _ouvrir(uploaded):
    taille = getattr(uploaded, "size", None)
    if taille is not None and taille > settings.MAX_PROOF_SIZE:
        limite = settings.MAX_PROOF_SIZE // (1024 * 1024)
        raise ValueError(f"Classeur trop volumineux (maximum {limite} Mo).")
    try:
        return load_workbook(uploaded, read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(f"Classeur illisible : {exc}") from exc


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
                raise ValueError(f"En-têtes manquants : {', '.join(manquantes)}")
            return numero, positions
    raise ValueError(
        "Ligne d'en-tête introuvable : le classeur doit porter les colonnes "
        + ", ".join(COLONNES_OBLIGATOIRES)
        + f" dans ses {LIGNES_D_ENTETE_MAX} premières lignes."
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
                f"Le classeur dépasse {LIGNES_MAX} lignes : scindez-le."
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
            raise ValueError("Montant de dépense obligatoire.")
        return amount, "", None, None
    if not devise or montant is None:
        raise ValueError(
            "Indiquez à la fois la devise et le montant d'origine, ou aucun des deux."
        )
    if devise == country.currency:
        return montant, "", None, None
    converti, taux = convert(montant, devise, country.currency, date.date())
    if converti is None:
        raise ValueError(
            f"Aucun taux connu pour convertir {devise} en {country.currency} "
            f"au {date.date().strftime('%d/%m/%Y')}."
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


def _empreinte(number, date, title, amount):
    return (number, date, title, amount)


def _lignes_en_base(dossier, cache):
    """Empreintes des lignes déjà présentes dans un dossier, lues une fois."""
    if dossier.pk not in cache:
        cache[dossier.pk] = {
            _empreinte(dossier.number, *valeurs)
            for valeurs in dossier.expenses.values_list("date", "title", "amount")
        }
    return cache[dossier.pk]


def _resoudre_le_pays(row, avec_colonne_pays, pays_par_nom, pays_impose, access):
    """Le pays de la ligne : la colonne PAYS, à défaut celui de la requête."""
    pays_nom = _texte(row["PAYS"]) if avec_colonne_pays else ""
    if not pays_nom:
        if pays_impose is None:
            raise ValueError("Pays obligatoire : la colonne PAYS est vide.")
        return pays_impose
    country = pays_par_nom.get(pays_nom.casefold())
    if country is None:
        raise ValueError(f"Pays « {pays_nom} » inconnu")
    if not access.has_global_scope and country.pk not in access.country_ids:
        raise ValueError(f"Pays « {country.name} » hors périmètre")
    return country


def importer_depenses(uploaded, user, dry_run=False, country=None):
    """Valide tout le classeur, puis le crée atomiquement si demandé.

    ``country`` est le pays de l'import, déjà vérifié contre le périmètre
    par la vue. Il est obligatoire quand le classeur n'a pas de colonne
    PAYS — le cas du fichier historique — et sert de repli quand la cellule
    PAYS d'une ligne est vide.
    """
    try:
        lignes, colonnes = _charger_lignes(uploaded)
    except ValueError as exc:
        return _resultat(0, 0, [_erreur(1, str(exc))], dry_run)

    avec_colonne_pays = "PAYS" in colonnes
    if not avec_colonne_pays and country is None:
        return _resultat(
            0, 0,
            [_erreur(1, "Le classeur n'a pas de colonne PAYS : indiquez le pays "
                        "de l'import (paramètre « country »).")],
            dry_run,
        )

    access = get_access(user)
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
    dossiers_existants = {}
    # Lignes déjà en base ou déjà vues dans ce classeur : réimporter le même
    # fichier — ou le même classeur collé deux fois — ne doit rien créer.
    empreintes_vues = {}
    lignes_en_base = {}

    for numero_ligne, row in lignes:
        try:
            number = _numero_d_ordre(row)
            pays_ligne = _resoudre_le_pays(
                row, avec_colonne_pays, pays, country, access
            )

            date_ligne = _date(row["DATE"])
            amount = _montant(row["DEPENSES"], "DEPENSES")
            title = _texte_borne(row, "LIBELLE DES TRANSACTIONS") or "Dépense importée"
            amount, devise, montant_origine, taux = _devise_d_origine(
                row, pays_ligne, date_ligne, amount
            )
            team_name = _texte_borne(row, "TEAM")
            cle_equipe = (pays_ligne.pk, team_name.casefold()) if team_name else None
            team = equipes.get(cle_equipe) if team_name else None
            if team_name and team is None:
                equipes_a_creer.setdefault(cle_equipe, (pays_ligne, team_name))
            owner_name = _texte_borne(row, "OWNER")
            cle_manager = (pays_ligne.pk, owner_name.casefold()) if owner_name else None
            owner = managers.get(cle_manager) if owner_name else None
            if owner_name and owner is None:
                managers_a_creer.setdefault(cle_manager, (pays_ligne, owner_name))

            # Le N°ORDRE est unique par pays : le dossier se cherche dans le
            # pays de la ligne, jamais ailleurs.
            cle_dossier = (pays_ligne.pk, number)
            if cle_dossier not in dossiers_existants:
                dossiers_existants[cle_dossier] = Dossier.objects.filter(
                    country=pays_ligne, number=number
                ).first()
            dossier = dossiers_existants[cle_dossier]
            if dossier is not None and dossier.status != Status.DRAFT:
                raise ValueError(f"Le dossier « {number} » est déjà déclaré")

            empreinte = _empreinte(cle_dossier, date_ligne, title, amount)
            deja = empreintes_vues.get(empreinte)
            if deja is not None:
                raise ValueError(f"Ligne identique à la ligne {deja} du classeur")
            if dossier is not None and _empreinte(
                number, date_ligne, title, amount
            ) in _lignes_en_base(dossier, lignes_en_base):
                raise ValueError(
                    f"Ligne déjà présente dans le dossier « {number} » : "
                    "même date, même libellé, même montant"
                )
            empreintes_vues[empreinte] = numero_ligne

            valides.append({
                "cle_dossier": cle_dossier,
                "number": number,
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

    nouveaux_dossiers = len({
        ligne["cle_dossier"] for ligne in valides
        if dossiers_existants[ligne["cle_dossier"]] is None
    })
    resultat = _resultat(
        nouveaux_dossiers, len(valides), erreurs, dry_run,
        equipes_creees=len(equipes_a_creer), managers_crees=len(managers_a_creer),
    )
    if erreurs or dry_run:
        return resultat

    with transaction.atomic():
        # Le référentiel manquant d'abord : les lignes s'y rattachent.
        # ``create`` un par un, et non ``bulk_create`` : la création doit
        # passer par les signaux d'historisation (``ChangeLog``).
        for cle, (pays_equipe, nom) in equipes_a_creer.items():
            equipes[cle] = Team.objects.create(country=pays_equipe, name=nom)
        for cle, (pays_manager, nom) in managers_a_creer.items():
            manager = Manager.objects.create(name=nom)
            pays_manager.managers.add(manager)
            managers[cle] = manager

        dossiers = {}
        depenses = []
        for ligne in valides:
            if ligne["team"] is None and ligne["cle_equipe"] is not None:
                ligne["team"] = equipes[ligne["cle_equipe"]]
            if ligne["owner"] is None and ligne["cle_manager"] is not None:
                ligne["owner"] = managers[ligne["cle_manager"]]
            dossier = dossiers.get(ligne["cle_dossier"])
            if dossier is None:
                dossier = dossiers_existants[ligne["cle_dossier"]]
                if dossier is None:
                    dossier = Dossier.objects.create(
                        number=ligne["number"],
                        label=ligne["title"] or ligne["number"],
                        country=ligne["country"],
                        team=ligne["team"],
                        owner=ligne["owner"],
                        date=ligne["date"].date(),
                        status=Status.DRAFT,
                        created_by=user.username,
                    )
                dossiers[ligne["cle_dossier"]] = dossier
            depenses.append(
                Expense(
                    dossier=dossier,
                    country=ligne["country"],
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
                )
            )
        # Aucun signal n'écoute ``Expense`` : l'insertion par lots ne fait
        # perdre aucune trace, et évite une requête par ligne.
        Expense.objects.bulk_create(depenses, batch_size=TAILLE_LOT)
    return resultat


def _resultat(dossiers, lignes, erreurs, dry_run, *, equipes_creees=0, managers_crees=0):
    return {
        "dossiers_crees": dossiers,
        "lignes_creees": lignes,
        "equipes_creees": equipes_creees,
        "managers_crees": managers_crees,
        "erreurs": erreurs,
        "dry_run": dry_run,
    }


def audit_import(request, resultat, country=None):
    AuditLog.objects.create(
        user=request.user.username,
        action=AuditLog.Action.IMPORTED,
        object_type="ExpenseImport",
        object_id=0,
        label="Import des dépenses Excel",
        # Le pays de l'import, quand il vient de la requête : le journal
        # d'un pays doit montrer ce qui y a été versé.
        country=country,
        detail=resultat,
        ip_address=client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:250],
    )
