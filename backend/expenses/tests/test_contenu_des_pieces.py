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
