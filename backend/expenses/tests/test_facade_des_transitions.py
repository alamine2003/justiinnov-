"""``expenses.transitions`` découpé en six modules, sous une façade (décision 131).

L'écart 19 de la revue d'architecture était gardé à dessein : vues, import,
commandes, migrations et documentation désignent ``transitions.<nom>``. Le
découpage ne tient que si chacun de ces noms se lit toujours au même endroit,
et si le module commun reste une feuille — un import circulaire ne se
découvrirait qu'au démarrage.
"""

import ast
from pathlib import Path

from django.test import SimpleTestCase

from expenses import (
    circuit,
    controle_des_pieces,
    exigences,
    rectifications,
    retrait,
    saisie,
    transitions,
)

#: Les noms que ``expenses/transitions.py`` définissait avant le découpage
#: (relevés sur la 2.4.10), plus ``PROOF_LOCKED_STATUSES`` qu'il importait et
#: que ``expenses.pieces`` y lit.
NOMS_D_AVANT = """
MOTIF_MANQUANT SANS_PREUVE AUDIT_ACTIONS PROOF_AUDIT_ACTIONS Resultat
exiger_l_auteur_du_brouillon VERROUILLE exiger_un_brouillon exiger_les_quatre_yeux
exiger_une_ligne_jamais_rectifiee sans_preuve exiger_un_dossier_ouvert _detail
verrouiller verrouiller_le_dossier_vise AJOUT_PAR_L_AUTEUR preparer_l_ajout
preparer_la_modification preparer_la_modification_du_dossier relire_sous_verrou
_verrouiller_le_dossier _instantane_du_dossier _exiger_les_lignes
_exiger_equipe_et_owner _exiger_les_auteurs_des_lignes _soumettre_les_lignes
_rouvrir_les_lignes _avant_sur_le_dossier _appliquer_au_dossier
_apres_sur_le_dossier _verrouiller_la_ligne _instantane_de_la_ligne
_avant_sur_la_ligne _appliquer_a_la_ligne _apres_sur_la_ligne _CIRCUITS
_transition soumettre rouvrir mettre_en_controle trancher cloturer _SERVICES
executer renommer retirer_brouillon _retirer_le_contenu _retirer_les_pieces
controler_piece _exiger_le_perimetre verifier_la_decision_de_rectification
peut_decider_rectification _verrouiller_la_demande _journaliser_la_demande
_decider_la_demande demander_rectification approuver_rectification
refuser_rectification PROOF_LOCKED_STATUSES
""".split()

MODULES = (exigences, circuit, saisie, retrait, controle_des_pieces, rectifications)


class FacadeDesTransitionsTests(SimpleTestCase):
    def test_chaque_nom_d_avant_se_lit_sur_la_facade(self):
        self.assertEqual(len(NOMS_D_AVANT), 59)
        for nom in NOMS_D_AVANT:
            with self.subTest(nom=nom):
                self.assertTrue(hasattr(transitions, nom))

    def test_la_facade_rend_l_objet_de_son_module_pas_une_copie(self):
        """Un service et son registre (``_CIRCUITS``, ``_SERVICES``) sont les
        mêmes objets, d'où qu'on les lise."""
        for module in MODULES:
            for nom, valeur in vars(module).items():
                if getattr(valeur, "__module__", None) == module.__name__:
                    with self.subTest(module=module.__name__, nom=nom):
                        self.assertIs(getattr(transitions, nom), valeur)
        self.assertIs(transitions._CIRCUITS, circuit._CIRCUITS)
        self.assertIs(transitions._SERVICES, circuit._SERVICES)

    def test_la_facade_n_expose_pas_les_outils_qu_on_remplace_en_test(self):
        """Remplacer ``transitions.record`` ne changerait plus rien : le
        circuit appelle le sien. Absent de la façade, un tel remplacement
        échoue bruyamment au lieu de laisser passer un test qui ne teste rien."""
        for nom in ("record", "exiger_la_capacite", "enregistrer", "triggers"):
            with self.subTest(nom=nom):
                self.assertFalse(hasattr(transitions, nom))

    def test_le_module_commun_n_importe_aucun_voisin(self):
        """``exigences`` est importé par tous : s'il importait l'un d'eux,
        le premier import de ``expenses`` tournerait en rond."""
        voisins = {m.__name__.rsplit(".", 1)[1] for m in MODULES} | {"transitions"}
        arbre = ast.parse(Path(exigences.__file__).read_text(encoding="utf-8"))
        importes = {
            noeud.module
            for noeud in ast.walk(arbre)
            if isinstance(noeud, ast.ImportFrom) and noeud.level == 1 and noeud.module
        }
        self.assertEqual(importes & voisins, set())
