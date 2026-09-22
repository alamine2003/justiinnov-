"""Le contenu d'une pièce doit confirmer son extension.

Un fichier HTML nommé ``recu.pdf`` serait sinon enregistré tel quel, puis
rejoué dans l'aperçu du siège, dans l'origine de l'application. Le type
MIME enregistré vient du contenu vérifié, jamais de l'en-tête du client.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from expenses.models import Proof

from .base import ExpenseTestCase

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class ContenuDesPiecesTests(ExpenseTestCase):
    def _deposer(self, nom, contenu, content_type="application/octet-stream"):
        self.login(self.owner)
        return self.client.post(
            "/api/proofs/",
            {"dossier": self.dossier.pk, "kind": "invoice",
             "file": SimpleUploadedFile(nom, contenu, content_type=content_type)},
            format="multipart",
        )

    def test_un_html_deguise_en_pdf_est_refuse(self):
        response = self._deposer("recu.pdf", b"<html><script>alert(1)</script></html>", "application/pdf")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("file", response.data)
        self.assertFalse(Proof.objects.exists())

    def test_le_type_enregistre_vient_du_contenu(self):
        """Le client déclare ``text/html`` sur un vrai PDF : c'est le PDF
        qui est enregistré, et servi comme tel."""
        response = self._deposer("recu.pdf", PDF, "text/html")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Proof.objects.get().content_type, "application/pdf")

    def test_les_images_et_les_textes_sont_verifies_aussi(self):
        self.assertEqual(self._deposer("photo.png", PNG).status_code, status.HTTP_201_CREATED)
        self.assertEqual(self._deposer("photo2.png", PDF).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._deposer("notes.txt", b"Re\xc3\xa7u du 3 mars").status_code, status.HTTP_201_CREATED)
        self.assertEqual(self._deposer("page.txt", b"  <!DOCTYPE html><p>x</p>").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._deposer("bin.csv", b"a;b\x00c").status_code, status.HTTP_400_BAD_REQUEST)


def _zip(membres):
    """Une archive ZIP en mémoire, avec les membres donnés (nom → contenu)."""
    from io import BytesIO
    from zipfile import ZipFile

    contenu = BytesIO()
    with ZipFile(contenu, "w") as archive:
        for nom, octets in membres.items():
            archive.writestr(nom, octets)
    return contenu.getvalue()


class SignaturesStrictesTests(ExpenseTestCase):
    """Un en-tête ne suffit pas : un ZIP quelconque n'est pas un document
    Office, un MP4 n'est pas une image HEIC, un fichier vide n'est pas un
    texte."""

    def _deposer(self, nom, contenu):
        self.login(self.owner)
        return self.client.post(
            "/api/proofs/",
            {"dossier": self.dossier.pk, "kind": "invoice",
             "file": SimpleUploadedFile(nom, contenu, content_type="application/octet-stream")},
            format="multipart",
        )

    def test_un_zip_quelconque_nomme_docx_est_refuse(self):
        response = self._deposer("recu.docx", _zip({"malice.html": b"<script>alert(1)</script>"}))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("file", response.data)
        self.assertFalse(Proof.objects.exists())

    def test_un_docx_minimal_est_accepte(self):
        docx = _zip({
            "[Content_Types].xml": b'<?xml version="1.0"?><Types/>',
            "word/document.xml": b'<?xml version="1.0"?><w:document/>',
        })

        response = self._deposer("recu.docx", docx)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(
            Proof.objects.get().content_type,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    def test_un_xlsx_exige_son_repertoire(self):
        classeur = _zip({"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<workbook/>"})
        document = _zip({"[Content_Types].xml": b"<Types/>", "word/document.xml": b"<w:document/>"})

        self.assertEqual(self._deposer("etat.xlsx", classeur).status_code, status.HTTP_201_CREATED)
        self.assertEqual(self._deposer("etat2.xlsx", document).status_code, status.HTTP_400_BAD_REQUEST)

    def test_un_heic_porte_sa_marque(self):
        image = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 24
        video = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 24

        self.assertEqual(self._deposer("photo.heic", image).status_code, status.HTTP_201_CREATED)
        self.assertEqual(self._deposer("film.heic", video).status_code, status.HTTP_400_BAD_REQUEST)

    def test_un_texte_vide_ou_html_est_refuse(self):
        self.assertEqual(self._deposer("vide.txt", b"").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self._deposer("blanc.csv", b"   \n").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            self._deposer("page.txt", b"  \n<script>x</script>").status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(self._deposer("liste.csv", b"date;montant\n").status_code, status.HTTP_201_CREATED)

    def test_un_document_ole_est_accepte_sur_son_en_tete(self):
        """``.doc`` et ``.xls`` : l'en-tête OLE, sans lire le conteneur."""
        ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 24

        self.assertEqual(self._deposer("ancien.doc", ole).status_code, status.HTTP_201_CREATED)
