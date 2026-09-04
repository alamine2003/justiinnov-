"""Import du classeur Excel produit par l'export des dépenses.

Tout ce qui entre par ici arrive en brouillon, sans montant justifié : le
classeur déclare, le siège constate. Chaque ligne est validée séparément et
signalée par son numéro de ligne ; rien n'est écrit tant qu'une seule ligne
est en erreur.
"""

import logging
from datetime import datetime
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

from .exports import EXPENSE_COLUMNS

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

ENTETES = [title for title, _ in EXPENSE_COLUMNS]

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
}

#: Chiffres avant la virgule autorisés par ``DecimalField(16, 2)``.
CHIFFRES_ENTIERS_MAX = (
    Expense._meta.get_field("amount").max_digits
    - Expense._meta.get_field("amount").decimal_places
)
CENTS = Decimal("0.01")


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
    if isinstance(value, datetime):
        return timezone.make_aware(value) if timezone.is_naive(value) else value
    try:
        return timezone.make_aware(
            datetime.strptime(_texte(value), "%d/%m/%Y %H:%M")
        )
    except (TypeError, ValueError):
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


def _charger_lignes(uploaded):
    workbook = _ouvrir(uploaded)
    sheet = workbook["BASE DE DONNEES ACTIONS"] if "BASE DE DONNEES ACTIONS" in workbook.sheetnames else workbook.active
    rows = sheet.iter_rows(values_only=True)
    try:
        header_row = next(rows)
    except StopIteration as exc:
        raise ValueError("Le classeur est vide.") from exc
    headers = [_texte(value) for value in header_row]
    missing = [entete for entete in ENTETES if entete not in headers]
    if missing:
        raise ValueError(f"En-têtes manquants : {', '.join(missing)}")
    positions = {entete: headers.index(entete) for entete in ENTETES}
    lignes = []
    for line_number, row in enumerate(rows, start=2):
        if not any(value not in (None, "") for value in row):
            continue
        if (
            _texte(row[positions["N°ORDRE"]] if positions["N°ORDRE"] < len(row) else None) == ""
            and _texte(row[positions["LIBELLE DES TRANSACTIONS"]] if positions["LIBELLE DES TRANSACTIONS"] < len(row) else None).upper() == "TOTAL"
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
                    entete: row[position] if position < len(row) else None
                    for entete, position in positions.items()
                },
            )
        )
    return lignes


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


def _empreinte(number, date, title, amount):
    return (number, date, title, amount)


def _lignes_en_base(dossier, cache):
    """Empreintes des lignes déjà présentes dans un dossier, lues une fois."""
    if dossier.number not in cache:
        cache[dossier.number] = {
            _empreinte(dossier.number, *valeurs)
            for valeurs in dossier.expenses.values_list("date", "title", "amount")
        }
    return cache[dossier.number]


def importer_depenses(uploaded, user, dry_run=False):
    """Valide tout le classeur, puis le crée atomiquement si demandé."""
    try:
        lignes = _charger_lignes(uploaded)
    except ValueError as exc:
        return {"dossiers_crees": 0, "lignes_creees": 0, "erreurs": [_erreur(1, str(exc))], "dry_run": dry_run}

    access = get_access(user)
    pays = {country.name.casefold(): country for country in Country.objects.all()}
    equipes = {(team.country_id, team.name.casefold()): team for team in Team.objects.all()}
    managers = _managers_par_pays()
    erreurs = []
    valides = []
    dossiers_existants = {}
    # Lignes déjà en base ou déjà vues dans ce classeur : réimporter le même
    # fichier — ou le même classeur collé deux fois — ne doit rien créer.
    empreintes_vues = {}
    lignes_en_base = {}

    for numero_ligne, row in lignes:
        try:
            number = _texte_borne(row, "N°ORDRE")
            if not number:
                raise ValueError("N°ORDRE obligatoire.")
            pays_nom = _texte(row["PAYS"])
            country = pays.get(pays_nom.casefold())
            if country is None:
                raise ValueError(f"Pays « {pays_nom} » inconnu")
            if not access.has_global_scope and country.pk not in access.country_ids:
                raise ValueError(f"Pays « {country.name} » hors périmètre")

            date = _date(row["DATE"])
            amount = _montant(row["DEPENSES"], "DEPENSES")
            title = _texte_borne(row, "LIBELLE DES TRANSACTIONS") or "Dépense importée"
            amount, devise, montant_origine, taux = _devise_d_origine(
                row, country, date, amount
            )
            team_name = _texte(row["TEAM"])
            team = equipes.get((country.pk, team_name.casefold())) if team_name else None
            if team_name and team is None:
                raise ValueError(f"Équipe « {team_name} » inconnue")
            owner_name = _texte(row["OWNER"])
            owner = managers.get((country.pk, owner_name.casefold())) if owner_name else None
            if owner_name and owner is None:
                raise ValueError(f"Manager « {owner_name} » inconnu pour {country.name}")

            dossier = dossiers_existants.get(number)
            if dossier is None:
                dossier = Dossier.objects.filter(number=number).first()
                dossiers_existants[number] = dossier
            if dossier is not None:
                if dossier.country_id != country.pk:
                    # Le dossier est peut-être celui d'un autre pays : le dire
                    # révélerait son existence à qui n'a pas à la connaître.
                    raise ValueError(
                        f"Le N°ORDRE « {number} » ne peut pas être utilisé pour cette ligne"
                    )
                if dossier.status != Status.DRAFT:
                    raise ValueError(f"Le dossier « {number} » est déjà déclaré")

            empreinte = _empreinte(number, date, title, amount)
            deja = empreintes_vues.get(empreinte)
            if deja is not None:
                raise ValueError(f"Ligne identique à la ligne {deja} du classeur")
            if dossier is not None and empreinte in _lignes_en_base(dossier, lignes_en_base):
                raise ValueError(
                    f"Ligne déjà présente dans le dossier « {number} » : "
                    "même date, même libellé, même montant"
                )
            empreintes_vues[empreinte] = numero_ligne

            valides.append({
                "number": number,
                "country": country,
                "team": team,
                "owner": owner,
                "date": date,
                "title": title,
                "amount": amount,
                "original_currency": devise,
                "original_amount": montant_origine,
                "original_rate": taux,
            })
        except ValueError as exc:
            erreurs.append(_erreur(numero_ligne, str(exc)))

    nouveaux_dossiers = len({ligne["number"] for ligne in valides if dossiers_existants[ligne["number"]] is None})
    resultat = {
        "dossiers_crees": nouveaux_dossiers,
        "lignes_creees": len(valides),
        "erreurs": erreurs,
        "dry_run": dry_run,
    }
    if erreurs or dry_run:
        return resultat

    with transaction.atomic():
        dossiers = {}
        depenses = []
        for ligne in valides:
            dossier = dossiers.get(ligne["number"])
            if dossier is None:
                dossier = dossiers_existants[ligne["number"]]
                if dossier is None:
                    dossier = Dossier.objects.create(
                        number=ligne["number"],
                        label=ligne["title"] or ligne["number"],
                        country=ligne["country"],
                        team=ligne["team"],
                        owner=ligne["owner"],
                        date=ligne["date"].date(),
                        status=Status.DRAFT,
                    )
                dossiers[ligne["number"]] = dossier
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
                    status=Status.DRAFT,
                    created_by=user.username,
                )
            )
        # Aucun signal n'écoute ``Expense`` : l'insertion par lots ne fait
        # perdre aucune trace, et évite une requête par ligne.
        Expense.objects.bulk_create(depenses, batch_size=TAILLE_LOT)
    return resultat


def audit_import(request, resultat):
    AuditLog.objects.create(
        user=request.user.username,
        action=AuditLog.Action.IMPORTED,
        object_type="ExpenseImport",
        object_id=0,
        label="Import des dépenses Excel",
        detail=resultat,
        ip_address=client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:250],
    )
