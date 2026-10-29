"""Les tableaux de pilotage de Grafana (décision 122).

Ils sont produits par ``deploy/grafana/pilotage.py`` : le JSON du dépôt doit
être celui que produit le générateur, et chaque requête de chaque panneau
doit s'exécuter sous les droits du rôle du BI, variables remplacées comme
Grafana les remplace — une colonne renommée dans une vue casse ce test, pas
le tableau de la direction.
"""

import importlib.util
import json
import re
from pathlib import Path

from django.conf import settings

from .test_bi import SousLeRoleDuBI

GRAFANA = Path(settings.BASE_DIR).parent / "deploy" / "grafana"


def _generateur():
    spec = importlib.util.spec_from_file_location("pilotage", GRAFANA / "pilotage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pilotage = _generateur()


def _requetes(tableau):
    """Les requêtes d'un tableau : variables, puis panneaux."""
    for variable in tableau["templating"]["list"]:
        yield f"variable {variable['name']}", variable["query"]
    for panneau in tableau["panels"]:
        for cible in panneau.get("targets", []):
            yield panneau["title"], cible["rawSql"]


def _interpoler(sql, annee, pays, types):
    """Ce que fait Grafana : ``$annee``, ``${pays:csv}``, ``${type_projet:sqlstring}``."""
    sql = sql.replace("${pays:csv}", ",".join(str(p) for p in pays))
    sql = sql.replace("${type_projet:sqlstring}", types)
    sql = sql.replace("$annee", str(annee))
    reste = re.findall(r"\$\{?\w+", sql)
    assert not reste, f"variable inconnue : {reste}"
    return sql


class TableauxDePilotageTests(SousLeRoleDuBI):
    def test_le_json_du_depot_est_celui_du_generateur(self):
        for nom, contenu in pilotage.rendus().items():
            with self.subTest(tableau=nom):
                fichier = GRAFANA / "dashboards" / "pilotage" / nom
                self.assertTrue(fichier.exists(), f"{nom} manque : python3 deploy/grafana/pilotage.py")
                self.assertEqual(
                    fichier.read_text(encoding="utf-8"), contenu,
                    f"{nom} diffère du générateur : python3 deploy/grafana/pilotage.py",
                )

    def test_les_tableaux_sont_dans_le_dossier_et_rien_d_autre(self):
        presents = {f.name for f in (GRAFANA / "dashboards" / "pilotage").glob("*.json")}
        self.assertEqual(presents, set(pilotage.TABLEAUX))

    def test_chaque_panneau_lit_la_source_du_bi(self):
        for nom, fabrique in pilotage.TABLEAUX.items():
            tableau = fabrique()
            identifiants = [p["id"] for p in tableau["panels"]]
            self.assertEqual(len(identifiants), len(set(identifiants)), nom)
            for panneau in tableau["panels"]:
                if panneau["type"] == "row":
                    continue
                with self.subTest(tableau=nom, panneau=panneau["title"]):
                    self.assertEqual(panneau["datasource"], {"type": "grafana-postgresql-datasource",
                                                             "uid": "bi"})
                    self.assertLessEqual(panneau["gridPos"]["x"] + panneau["gridPos"]["w"], 24)

    def test_chaque_requete_s_execute_sous_le_role_du_bi(self):
        annee = self.year
        tous_les_pays = [self.togo.pk, self.ivoire.pk, self.rdc.pk, self.gabon.pk]
        cas = [
            ("tout", tous_les_pays, pilotage.TOUS),
            ("un pays, un type", [self.togo.pk], "'congres'"),
            ("deux types", tous_les_pays, "'congres','voyage'"),
        ]
        executees = 0
        for nom, fabrique in pilotage.TABLEAUX.items():
            for titre, sql in _requetes(fabrique()):
                for libelle, pays, types in cas:
                    with self.subTest(tableau=nom, panneau=titre, cas=libelle):
                        resultat = self.en_tant_que_bi(_interpoler(sql, annee, pays, types))
                        self.assertNotIsInstance(resultat, Exception, f"{titre} : {resultat}")
                        executees += 1
        self.assertGreater(executees, 100)

    def test_la_vue_d_ensemble_rend_les_chiffres_du_consolide(self):
        tableau = pilotage.vue_d_ensemble()
        attribue = next(p for p in tableau["panels"] if p["title"] == "Attribué (FCFA)")
        rendu = self.en_tant_que_bi(
            _interpoler(attribue["targets"][0]["rawSql"], self.year, [], "")
        )
        attendu = self.en_tant_que_bi(
            f"SELECT attribue_xof FROM bi.consolidation WHERE annee = {self.year}"
        )
        self.assertEqual(rendu, attendu)
        self.assertTrue(rendu)

    def test_le_json_se_relit(self):
        for nom in pilotage.TABLEAUX:
            json.loads((GRAFANA / "dashboards" / "pilotage" / nom).read_text(encoding="utf-8"))
