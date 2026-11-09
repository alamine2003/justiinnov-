"""Une pièce est ce qu'elle prétend être : ses premiers octets le confirment.

Décision 45. Le type MIME enregistré vient du serveur, jamais du client : un
fichier HTML nommé ``recu.pdf`` serait sinon rejoué tel quel dans l'aperçu
du siège, dans l'origine de l'application.

Chaque extension acceptée a sa **vérification** et son type MIME, dans la
table :data:`FORMATS` (décision 124). Accepter un format de plus, c'est
ajouter une ligne à cette table — et à ``ALLOWED_PROOF_EXTENSIONS`` — sans
rouvrir :func:`type_verifie`.

``.doc`` et ``.xls`` ne sont reconnus qu'à leur en-tête OLE, commun à tout
document Office binaire (Word, Excel, PowerPoint, Outlook…) : le format ne
dit pas plus sans lire le répertoire du conteneur, et un classeur nommé
``.doc`` reste un document Office, pas un HTML déguisé.
"""

import zipfile

#: Ce qu'on lit du fichier pour en juger : assez pour toutes les en-têtes.
TAILLE_DE_L_EN_TETE = 4096

_DEBUTS_HTML = (b"<!doctype", b"<html", b"<script", b"<svg")
#: Marques HEIF acceptées après ``ftyp`` : les images HEIC et leurs
#: conteneurs (``mif1``, ``msf1``) ; un MP4 porte aussi ``ftyp``, pas elles.
_MARQUES_HEIC = {b"heic", b"heix", b"mif1", b"msf1"}


def commence_par(*debuts):
    """L'en-tête commence par l'une des signatures."""
    def verifier(tete, uploaded):
        return any(tete.startswith(debut) for debut in debuts)
    return verifier


def texte(tete, uploaded):
    """Du texte : non vide, sans octet nul, et pas une page HTML."""
    contenu = tete.lstrip()
    if not contenu or b"\x00" in tete:
        return False
    return not contenu.lower().startswith(_DEBUTS_HTML)


def webp(tete, uploaded):
    return tete[:4] == b"RIFF" and tete[8:12] == b"WEBP"


def heic(tete, uploaded):
    return tete[4:8] == b"ftyp" and tete[8:12] in _MARQUES_HEIC


def office_ouvert(repertoire):
    """Un document Office ouvert : un ZIP qui contient le répertoire du
    format (``word/``, ``xl/``) — un ZIP quelconque renommé n'en a pas.

    Le premier membre ne suffit pas : ``[Content_Types].xml`` ouvre souvent
    le fichier, et son ordre n'est pas garanti. C'est le répertoire du
    conteneur qui dit ce qu'il est.
    """
    def verifier(tete, uploaded):
        if not tete.startswith(b"PK\x03\x04"):
            return False
        try:
            with zipfile.ZipFile(uploaded) as archive:
                noms = archive.namelist()
        except (zipfile.BadZipFile, OSError, ValueError):
            return False
        finally:
            uploaded.seek(0)
        return any(nom.startswith(repertoire) for nom in noms)
    return verifier


_OLE = commence_par(b"\xd0\xcf\x11\xe0")
_JPEG = commence_par(b"\xff\xd8\xff")

#: Extension → (vérification de l'en-tête, type MIME enregistré).
FORMATS = {
    ".pdf": (commence_par(b"%PDF"), "application/pdf"),
    ".jpg": (_JPEG, "image/jpeg"),
    ".jpeg": (_JPEG, "image/jpeg"),
    ".png": (commence_par(b"\x89PNG\r\n\x1a\n"), "image/png"),
    ".webp": (webp, "image/webp"),
    ".heic": (heic, "image/heic"),
    ".doc": (_OLE, "application/msword"),
    ".xls": (_OLE, "application/vnd.ms-excel"),
    ".docx": (
        office_ouvert("word/"),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    ".xlsx": (
        office_ouvert("xl/"),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    ".csv": (texte, "text/csv"),
    ".txt": (texte, "text/plain"),
}


def type_verifie(uploaded, extension):
    """Type MIME d'une pièce dont les premiers octets confirment l'extension.

    ``None`` quand le contenu ne correspond pas : un HTML déguisé en PDF, un
    texte vide ou qui commence par une balise, un binaire dans un ``.csv``,
    un ZIP quelconque nommé ``.docx``, une vidéo nommée ``.heic`` — ou une
    extension que la table ne connaît pas.
    """
    if extension not in FORMATS:
        return None
    verifier, mime = FORMATS[extension]
    tete = uploaded.read(TAILLE_DE_L_EN_TETE)
    uploaded.seek(0)
    return mime if verifier(tete, uploaded) else None
