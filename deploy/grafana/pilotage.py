#!/usr/bin/env python3
"""Génère les tableaux de bord « Pilotage » de Grafana (décision 122).

Six tableaux, en français, lus dans le schéma ``bi`` sous le rôle du BI :
vue d'ensemble, enveloppes, justification et preuves, activité et
tendances, contrôle, anomalies et traçabilité. Les JSON produits dans
``dashboards/pilotage/`` sont provisionnés tels quels ; on ne les retouche
pas dans Grafana (``allowUiUpdates: false``) ni à la main : on modifie ce
fichier, puis on régénère.

    python3 deploy/grafana/pilotage.py          # écrit les JSON
    python3 deploy/grafana/pilotage.py --verifier   # échoue s'ils diffèrent

Un test (backend/reporting/tests/test_bi_tableaux.py) exécute chaque
requête de chaque panneau sous les droits du rôle du BI, et vérifie que les
JSON du dépôt sont bien ceux que ce fichier produit.

Variables des requêtes, et elles seules : ``$annee`` (un entier),
``${pays:csv}`` (identifiants), ``${type_projet:sqlstring}``. Pas de macro
de temps : un exercice se choisit par l'année, comme dans l'application.
"""

import json
import sys
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent / "dashboards" / "pilotage"
SOURCE = {"type": "grafana-postgresql-datasource", "uid": "bi"}
#: Montant en FCFA : affiché en entier, séparé par milliers à la française
#: (unité ``locale`` de Grafana), et « (FCFA) » ajouté au titre du panneau.
#: Grafana n'a pas d'unité qui groupe les milliers *et* porte un suffixe.
FCFA = "FCFA"
#: Montant dans la devise du pays (tableau des enveloppes).
LOCALE = "locale"
TOUS = "'__tous'"

# --- Variables ---------------------------------------------------------------

ANNEE = {
    "name": "annee",
    "label": "Exercice",
    "type": "query",
    "datasource": SOURCE,
    "query": (
        "SELECT annee AS __value, annee::text AS __text FROM ("
        "SELECT annee FROM bi.consolidation_pays UNION "
        "SELECT annee FROM bi.lignes UNION "
        "SELECT extract(year FROM bi.aujourd_hui())::integer"
        ") AS exercices ORDER BY annee DESC"
    ),
    "definition": "Exercices",
    "refresh": 1,
    "sort": 0,
    "multi": False,
    "includeAll": False,
    "current": {},
    "options": [],
}

PAYS = {
    "name": "pays",
    "label": "Pays",
    "type": "query",
    "datasource": SOURCE,
    "query": "SELECT nom AS __text, id AS __value FROM bi.pays ORDER BY nom",
    "definition": "Pays",
    "refresh": 1,
    "sort": 0,
    "multi": True,
    "includeAll": True,
    "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
    "options": [],
}

TYPE_PROJET = {
    "name": "type_projet",
    "label": "Type de projet",
    "type": "query",
    "datasource": SOURCE,
    "query": (
        "SELECT DISTINCT type_projet AS __text, type_projet_code AS __value "
        "FROM bi.lignes WHERE type_projet_code IS NOT NULL ORDER BY 1"
    ),
    "definition": "Types de projets",
    "refresh": 1,
    "sort": 0,
    "multi": True,
    "includeAll": True,
    "allValue": TOUS,
    "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
    "options": [],
}

#: Filtres réutilisés dans les requêtes.
PAR_PAYS = "pays_id IN (${pays:csv})"
PAR_TYPE = (
    f"({TOUS} IN (${{type_projet:sqlstring}}) "
    "OR type_projet_code IN (${type_projet:sqlstring}))"
)


# --- Panneaux ----------------------------------------------------------------


class Grille:
    """Place les panneaux de gauche à droite, ligne par ligne (24 colonnes)."""

    def __init__(self):
        self.x = 0
        self.y = 0
        self.hauteur = 0
        self.panneaux = []

    def ajouter(self, panneau, largeur, hauteur):
        if self.x + largeur > 24:
            self.x = 0
            self.y += self.hauteur
            self.hauteur = 0
        panneau["id"] = len(self.panneaux) + 1
        panneau["gridPos"] = {"x": self.x, "y": self.y, "w": largeur, "h": hauteur}
        self.x += largeur
        self.hauteur = max(self.hauteur, hauteur)
        self.panneaux.append(panneau)

    def section(self, titre):
        if self.x:
            self.x = 0
            self.y += self.hauteur
            self.hauteur = 0
        self.ajouter({"type": "row", "title": titre, "collapsed": False, "panels": []}, 24, 1)
        self.x = 24  # la ligne suivante commence sous le titre


def _cible(sql, format_="table"):
    return [{
        "refId": "A",
        "datasource": SOURCE,
        "rawQuery": True,
        "editorMode": "code",
        "format": format_,
        "rawSql": " ".join(sql.split()),
    }]


#: Durée en jours : un nombre, et « (jours) » au titre. L'unité « d » de
#: Grafana passerait aux semaines, en anglais (« 5.0 weeks »).
JOURS = "jours"


def _unite(unite):
    return {FCFA: LOCALE, JOURS: "none"}.get(unite, unite)


def _titre(titre, unite):
    if unite == FCFA:
        return f"{titre} (FCFA)"
    if unite == JOURS and "(jours)" not in titre:
        return f"{titre} (jours)"
    return titre


def _defauts(unite=None, decimales=None, seuils=None, couleur=None):
    defaults = {"color": {"mode": couleur or "thresholds"}}
    if unite:
        defaults["unit"] = _unite(unite)
    if decimales is not None:
        defaults["decimals"] = decimales
    defaults["thresholds"] = {
        "mode": "absolute",
        "steps": seuils or [{"color": "blue", "value": None}],
    }
    return defaults


#: Seuils d'un taux d'exécution : vert, orange au seuil d'alerte courant,
#: rouge au dépassement. Le seuil exact est celui de la configuration ; le
#: tableau colore, la colonne « Niveau » dit le niveau calculé par le serveur.
SEUILS_EXECUTION = [
    {"color": "green", "value": None},
    {"color": "orange", "value": 0.8},
    {"color": "red", "value": 1.0000001},
]
SEUILS_JUSTIFICATION = [
    {"color": "red", "value": None},
    {"color": "orange", "value": 0.8},
    {"color": "green", "value": 0.95},
]


def stat(titre, sql, unite=None, decimales=0, seuils=None, description="", texte=False):
    """Une valeur ; ``texte`` : la requête rend un texte, pas un nombre."""
    return {
        "type": "stat",
        "title": _titre(titre, unite),
        "description": description,
        "datasource": SOURCE,
        "targets": _cible(sql),
        "fieldConfig": {"defaults": _defauts(unite, decimales, seuils), "overrides": []},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "/.*/" if texte else "",
                              "values": False},
            "colorMode": "value",
            "graphMode": "none",
            "justifyMode": "auto",
            "textMode": "value",
            "orientation": "auto",
        },
    }


#: Colonnes que les tableaux mettent en forme d'office, sauf mention
#: contraire : montants dans la devise du pays, dates et instants à la
#: française.
_DATE = ("time:DD/MM/YYYY", None, None, None)
_INSTANT = ("time:DD/MM/YYYY HH:mm", None, None, None)
COLONNES_PAR_DEFAUT = {
    "Montant": ("locale", 0, None, None),
    "Montant payé": ("locale", 0, None, None),
    "Montant imputé": ("locale", 0, None, None),
    "Seuil": ("locale", 0, None, None),
    "Date": _DATE,
    "Le": _INSTANT,
    "Demandée le": _INSTANT,
    "Soumise le": _INSTANT,
    "Dernière": _INSTANT,
    "Dernière connexion": _INSTANT,
}


def _colonnes_par_defaut(sql):
    return {nom: forme for nom, forme in COLONNES_PAR_DEFAUT.items() if f'AS "{nom}"' in sql}


def tableau(titre, sql, colonnes=None, description="", tri=None):
    """Un tableau ; ``colonnes`` : {nom: (unité, décimales, seuils, affichage)}."""
    colonnes = {**_colonnes_par_defaut(sql), **(colonnes or {})}
    surcharges = []
    for nom, (unite, decimales, seuils, affichage) in colonnes.items():
        proprietes = []
        if unite:
            proprietes.append({"id": "unit", "value": _unite(unite)})
        if decimales is not None:
            proprietes.append({"id": "decimals", "value": decimales})
        if seuils:
            proprietes.append({"id": "thresholds", "value": {"mode": "absolute", "steps": seuils}})
        if affichage:
            proprietes.append({"id": "custom.cellOptions", "value": {"type": affichage}})
        surcharges.append({"matcher": {"id": "byName", "options": nom}, "properties": proprietes})
    options = {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}
    if tri:
        options["sortBy"] = [{"displayName": tri[0], "desc": tri[1]}]
    en_fcfa = any(c[0] == FCFA for c in (colonnes or {}).values())
    return {
        "type": "table",
        "title": _titre(titre, FCFA if en_fcfa else None),
        "description": description,
        "datasource": SOURCE,
        "targets": _cible(sql),
        "fieldConfig": {
            "defaults": {**_defauts(), "custom": {"align": "auto", "filterable": True}},
            "overrides": surcharges,
        },
        "options": options,
    }


def barres(titre, sql, unite=None, horizontal=False, empile=False, description="", pivot=None):
    """Un histogramme ; ``pivot`` : (abscisse, série, valeur) d'une requête
    « longue », remise en colonnes par Grafana (une colonne par série)."""
    transformations = []
    if pivot:
        abscisse, serie, valeur = pivot
        transformations.append({
            "id": "groupingToMatrix",
            "options": {"rowField": abscisse, "columnField": serie, "valueField": valeur,
                        "emptyValue": "zero"},
        })
    return {
        "transformations": transformations,
        "type": "barchart",
        "title": _titre(titre, unite),
        "description": description,
        "datasource": SOURCE,
        "targets": _cible(sql),
        "fieldConfig": {
            "defaults": {**_defauts(unite, 0, couleur="palette-classic"),
                         "custom": {"fillOpacity": 80, "lineWidth": 1}},
            "overrides": [],
        },
        "options": {
            "orientation": "horizontal" if horizontal else "vertical",
            "stacking": "normal" if empile else "none",
            "showValue": "never",
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
            "tooltip": {"mode": "multi", "sort": "none"},
            "xTickLabelRotation": 0,
            "barWidth": 0.8,
            "groupWidth": 0.7,
        },
    }


def jauges(titre, sql, unite="percentunit", seuils=None, description=""):
    return {
        "type": "bargauge",
        "title": titre,
        "description": description,
        "datasource": SOURCE,
        "targets": _cible(sql),
        "fieldConfig": {
            "defaults": {**_defauts(unite, 1, seuils or SEUILS_EXECUTION), "min": 0},
            "overrides": [],
        },
        "options": {
            "orientation": "horizontal",
            "displayMode": "gradient",
            "showUnfilled": True,
            "reduceOptions": {"calcs": [], "fields": "", "values": True},
            "valueMode": "color",
            "namePlacement": "left",
        },
    }


def camembert(titre, sql, unite=None, description=""):
    return {
        "type": "piechart",
        "title": _titre(titre, unite),
        "description": description,
        "datasource": SOURCE,
        "targets": _cible(sql),
        "fieldConfig": {"defaults": _defauts(unite, 0, couleur="palette-classic"), "overrides": []},
        "options": {
            "pieType": "donut",
            "reduceOptions": {"calcs": [], "fields": "", "values": True},
            "legend": {"displayMode": "table", "placement": "right", "showLegend": True,
                       "values": ["value", "percent"]},
            "displayLabels": [],
            "tooltip": {"mode": "single", "sort": "none"},
        },
    }


def tableau_de_bord(uid, titre, description, grille, variables, liens=True):
    return {
        "uid": uid,
        "title": titre,
        "description": description,
        "tags": ["pilotage", "justi-gh"],
        "timezone": "browser",
        "editable": False,
        "graphTooltip": 1,
        "schemaVersion": 39,
        "version": 1,
        "refresh": "",
        "time": {"from": "now-1y", "to": "now"},
        "timepicker": {"hidden": True},
        "templating": {"list": variables},
        "annotations": {"list": []},
        "links": [{
            "title": "Pilotage",
            "type": "dashboards",
            "tags": ["pilotage"],
            "asDropdown": True,
            "includeVars": True,
            "keepTime": False,
        }] if liens else [],
        "panels": grille.panneaux,
    }


# --- Les six tableaux --------------------------------------------------------

#: Hauteur d'un panneau qui liste les pays : dix-sept filiales à terme.
PAR_PAYS_HAUTEUR = 15

MONTANT = (FCFA, 0, None, None)
DEVISE = (LOCALE, 0, None, None)
TAUX = ("percentunit", 1, SEUILS_EXECUTION, "color-text")
TAUX_JUSTIF = ("percentunit", 1, SEUILS_JUSTIFICATION, "color-text")

NOTE_CHIFFRES = (
    "Chiffres du serveur JUSTI GH, recalculés à chaque affichage : engagé = lignes "
    "soumises ou en contrôle ; consommé = justifiées, non justifiées ou clôturées ; "
    "un brouillon ne compte pas. Montants en FCFA au taux en vigueur au 31 décembre "
    "(exercice clos) ou à ce jour ; un pays sans taux est exclu du total et nommé."
)


def vue_d_ensemble():
    g = Grille()
    conso = "FROM bi.consolidation WHERE annee = $annee"
    g.ajouter(stat("Attribué", f"SELECT attribue_xof {conso}", FCFA,
                   description=NOTE_CHIFFRES), 4, 4)
    g.ajouter(stat("Engagé", f"SELECT engage_xof {conso}", FCFA), 4, 4)
    g.ajouter(stat("Consommé", f"SELECT consomme_xof {conso}", FCFA), 4, 4)
    g.ajouter(stat("Justifié", f"SELECT justifie_xof {conso}", FCFA), 4, 4)
    g.ajouter(stat("Écart non prouvé", f"SELECT ecart_xof {conso}", FCFA,
                   seuils=[{"color": "green", "value": None}, {"color": "red", "value": 1}],
                   description="Consommé moins justifié : l'argent dépensé dont la preuve manque."),
              4, 4)
    g.ajouter(stat("Disponible", f"SELECT disponible_xof {conso}", FCFA,
                   seuils=[{"color": "red", "value": None}, {"color": "green", "value": 0}]),
              4, 4)
    g.ajouter(stat("Taux d'exécution", f"SELECT taux_execution {conso}", "percentunit", 1,
                   SEUILS_EXECUTION, "(Consommé + engagé) / attribué."), 4, 4)
    g.ajouter(stat("Taux de justification", f"SELECT taux_justification {conso}",
                   "percentunit", 1, SEUILS_JUSTIFICATION, "Justifié / consommé."), 4, 4)
    g.ajouter(stat("À contrôler", "SELECT count(*) FROM bi.file_controle",
                   description="Lignes soumises ou en contrôle, tous exercices."), 4, 4)
    g.ajouter(stat("Dossiers ouverts",
                   "SELECT count(*) FROM bi.dossiers WHERE ouvert AND annee = $annee"), 4, 4)
    g.ajouter(stat("Alertes de justificatif",
                   "SELECT count(*) FROM bi.dossiers WHERE alerte IS NOT NULL",
                   seuils=[{"color": "green", "value": None}, {"color": "red", "value": 1}]), 4, 4)
    g.ajouter(stat("Devises sans taux",
                   f"SELECT coalesce(nullif(array_to_string(devises_non_converties, ', '), ''), "
                   f"'Aucun') {conso}",
                   description="Devises dont aucun taux n'est publié à la date de référence.",
                   texte=True),
              4, 4)
    g.section("Par pays")
    g.ajouter(tableau(
        "Consolidation par pays",
        """SELECT pays AS "Pays", devise AS "Devise", attribue_xof AS "Attribué",
                  engage_xof AS "Engagé", consomme_xof AS "Consommé", justifie_xof AS "Justifié",
                  ecart_xof AS "Écart", disponible_xof AS "Disponible",
                  taux_execution AS "Exécution", libelle_niveau AS "Niveau",
                  taux_justification AS "Justification", enveloppes_depassees AS "Enveloppes dépassées"
             FROM bi.consolidation_pays WHERE annee = $annee ORDER BY pays""",
        {"Attribué": MONTANT, "Engagé": MONTANT, "Consommé": MONTANT, "Justifié": MONTANT,
         "Écart": MONTANT, "Disponible": MONTANT, "Exécution": TAUX,
         "Justification": TAUX_JUSTIF},
        "Montants en FCFA ; un pays sans taux affiche des cases vides."), 24, PAR_PAYS_HAUTEUR)
    g.ajouter(jauges(
        "Taux d'exécution par pays",
        """SELECT pays AS "Pays", taux_execution AS "Exécution"
             FROM bi.consolidation_pays WHERE annee = $annee AND taux_execution IS NOT NULL
            ORDER BY taux_execution DESC"""), 12, PAR_PAYS_HAUTEUR)
    g.ajouter(barres(
        "Consommé et justifié par pays",
        """SELECT pays AS "Pays", consomme_xof AS "Consommé", justifie_xof AS "Justifié"
             FROM bi.consolidation_pays WHERE annee = $annee ORDER BY consomme_xof DESC NULLS LAST""",
        FCFA, horizontal=True), 12, PAR_PAYS_HAUTEUR)
    g.section("Alertes")
    g.ajouter(tableau(
        "Alertes en cours",
        """SELECT * FROM (
             SELECT CASE alerte WHEN 'budget_overrun' THEN 'Dépassement'
                                ELSE 'Seuil ' || seuil_atteint::integer || ' %' END AS "Alerte",
                    CASE gravite WHEN 'critical' THEN 'Critique' ELSE 'Avertissement' END AS "Gravité",
                    pays AS "Pays", cible AS "Objet",
                    coalesce(pourcentage_utilise::text || ' % utilisés', '') AS "Détail"
               FROM bi.enveloppes WHERE annee = $annee AND alerte IS NOT NULL
             UNION ALL
             SELECT CASE alerte WHEN 'proof_missing' THEN 'Justificatif manquant'
                                ELSE 'Justificatif incomplet' END,
                    CASE alerte WHEN 'proof_missing' THEN 'Critique' ELSE 'Avertissement' END,
                    pays, numero || ' — ' || libelle,
                    lignes_sans_preuve || ' ligne(s) sans preuve'
               FROM bi.dossiers WHERE alerte IS NOT NULL
             UNION ALL
             SELECT 'Dépense inhabituelle', 'Avertissement', pays, numero_dossier || ' — ' || libelle,
                    montant::text || ' ' || devise
               FROM bi.inhabituelles WHERE annee = $annee
           ) AS alertes ORDER BY "Gravité" DESC, "Pays" """), 24, 12)
    return tableau_de_bord(
        "bi-vue-ensemble", "Pilotage — vue d'ensemble",
        "Où en est l'argent des filiales : attribué, dépensé, prouvé, et ce qui demande attention.",
        g, [ANNEE])


def enveloppes():
    g = Grille()
    filtre = f"annee = $annee AND {PAR_PAYS}"
    g.ajouter(tableau(
        "Enveloppes",
        f"""SELECT pays AS "Pays", CASE portee WHEN 'pays' THEN 'Pays' WHEN 'projet' THEN 'Projet'
                                     WHEN 'equipe' THEN 'Équipe' ELSE 'Manager' END AS "Portée",
                   cible AS "Enveloppe", devise AS "Devise", montant AS "Montant",
                   engage AS "Engagé", consomme AS "Consommé", justifie AS "Justifié",
                   disponible AS "Disponible", taux_execution AS "Exécution",
                   libelle_niveau AS "Niveau",
                   CASE alerte WHEN 'budget_overrun' THEN 'Dépassement de ' || depassement::text
                               WHEN 'budget_threshold' THEN 'Seuil ' || seuil_atteint::integer || ' %'
                               ELSE '' END AS "Alerte",
                   CASE politique_depassement WHEN 'block' THEN 'Bloquer' WHEN 'warn' THEN 'Alerter'
                        ELSE 'Approbation' END AS "Politique"
              FROM bi.enveloppes WHERE {filtre} ORDER BY pays, portee DESC, cible""",
        {"Montant": DEVISE, "Engagé": DEVISE, "Consommé": DEVISE, "Justifié": DEVISE,
         "Disponible": DEVISE, "Exécution": TAUX},
        "Montants dans la devise du pays. Les réallocations approuvées sont déjà dans le montant."),
        24, 11)
    g.ajouter(barres(
        "Projection de fin d'exercice",
        f"""SELECT pays AS "Pays", attribue_xof AS "Attribué",
                   bi.arrondi((consomme_xof + engage_xof) /
                     greatest(least(bi.aujourd_hui(), make_date($annee, 12, 31))
                              - make_date($annee, 1, 1) + 1, 1)
                     * (make_date($annee, 12, 31) - make_date($annee, 1, 1) + 1), 0) AS "Projection"
              FROM bi.consolidation_pays WHERE {filtre} AND taux_xof IS NOT NULL ORDER BY pays""",
        FCFA, horizontal=True, description="Engagé et consommé ramenés à l'année entière au rythme observé depuis "
                          "le 1er janvier. Une projection au-dessus de l'attribué annonce un "
                          "dépassement si le rythme se maintient."), 12, PAR_PAYS_HAUTEUR)
    g.ajouter(barres(
        "Comparaison avec l'exercice précédent",
        """SELECT p.nom AS "Pays",
                   coalesce(sum(c.consomme_xof + c.engage_xof) FILTER (WHERE c.annee = $annee - 1), 0)
                     AS "Exercice précédent",
                   coalesce(sum(c.consomme_xof + c.engage_xof) FILTER (WHERE c.annee = $annee), 0)
                     AS "Exercice choisi"
              FROM bi.pays AS p JOIN bi.consolidation_pays AS c ON c.pays_id = p.id
             WHERE c.annee IN ($annee, $annee - 1) AND p.id IN (${pays:csv})
             GROUP BY p.nom ORDER BY p.nom""",
        FCFA, horizontal=True,
        description="Engagé et consommé, aux taux de chaque exercice."), 12, PAR_PAYS_HAUTEUR)
    g.ajouter(jauges(
        "Exécution des enveloppes de projet",
        f"""SELECT cible || ' (' || pays || ')' AS "Projet", taux_execution AS "Exécution"
              FROM bi.enveloppes WHERE {filtre} AND portee = 'projet' AND taux_execution IS NOT NULL
             ORDER BY taux_execution DESC LIMIT 20"""), 12, 10)
    g.ajouter(tableau(
        "Réallocations",
        f"""SELECT r.demandee_le AS "Demandée le", r.pays AS "Pays",
                   es.cible AS "De", ec.cible AS "Vers", r.montant AS "Montant",
                   r.devise AS "Devise", r.libelle_etat AS "État",
                   r.demandee_par AS "Demandée par", r.decidee_par AS "Décidée par"
              FROM bi.reallocations AS r
              LEFT JOIN bi.enveloppes AS es ON es.id = r.enveloppe_source_id
              LEFT JOIN bi.enveloppes AS ec ON ec.id = r.enveloppe_cible_id
             WHERE r.annee = $annee AND r.{PAR_PAYS} ORDER BY r.demandee_le DESC"""),
        12, 10)
    return tableau_de_bord(
        "bi-enveloppes", "Pilotage — enveloppes",
        "Consommation, dépassements, projection et comparaison des enveloppes.",
        g, [ANNEE, PAYS])


def justification():
    g = Grille()
    lignes = f"FROM bi.lignes WHERE annee = $annee AND {PAR_PAYS}"
    g.ajouter(stat("Taux de justification",
                   f"SELECT bi.ratio(sum(justifie_xof), sum(montant_xof)) {lignes} AND consommee",
                   "percentunit", 1, SEUILS_JUSTIFICATION,
                   "Justifié / consommé, sur les pays choisis."), 6, 4)
    g.ajouter(stat("Écart non prouvé",
                   f"SELECT coalesce(sum(montant_xof - justifie_xof), 0) {lignes} AND consommee",
                   FCFA), 6, 4)
    g.ajouter(stat("Lignes déclarées sans pièce",
                   f"SELECT count(*) {lignes} AND NOT brouillon AND NOT a_preuve",
                   seuils=[{"color": "green", "value": None}, {"color": "red", "value": 1}]), 6, 4)
    g.ajouter(stat("Pièces rejetées",
                   f"SELECT count(*) FROM bi.pieces WHERE annee = $annee AND {PAR_PAYS} "
                   "AND etat_code = 'rejected'"), 6, 4)
    g.ajouter(barres(
        "Dépensé et justifié par pays",
        f"""SELECT pays AS "Pays", sum(montant_xof) AS "Consommé", sum(justifie_xof) AS "Justifié"
              {lignes} AND consommee GROUP BY pays ORDER BY 2 DESC NULLS LAST""", FCFA,
        horizontal=True), 12, PAR_PAYS_HAUTEUR)
    g.ajouter(camembert(
        "Pièces par état",
        f"""SELECT etat AS "État", count(*) AS "Pièces" FROM bi.pieces
             WHERE annee = $annee AND {PAR_PAYS} GROUP BY etat ORDER BY 2 DESC"""), 6, 9)
    g.ajouter(camembert(
        "Pièces par type",
        f"""SELECT type AS "Type", count(*) AS "Pièces" FROM bi.pieces
             WHERE annee = $annee AND {PAR_PAYS} GROUP BY type ORDER BY 2 DESC"""), 6, 9)
    g.section("Délais")
    delais = f"FROM bi.delais WHERE annee = $annee AND {PAR_PAYS}"
    g.ajouter(stat("Dépense → soumission (médiane)",
                   f"SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY jours_depense_soumission) "
                   f"{delais}", JOURS, 1), 6, 4)
    g.ajouter(stat("Soumission → constat (médiane)",
                   f"SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY jours_soumission_constat) "
                   f"{delais}", JOURS, 1), 6, 4)
    g.ajouter(stat("Dépense → dépôt de la pièce (médiane)",
                   f"SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY jours_apres_depense) "
                   f"FROM bi.pieces WHERE annee = $annee AND {PAR_PAYS}", JOURS, 1), 6, 4)
    g.ajouter(stat("Réouvertures",
                   f"SELECT coalesce(sum(reouvertures), 0) {delais}"), 6, 4)
    g.ajouter(barres(
        "Délais médians par pays (jours)",
        f"""SELECT pays AS "Pays",
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY jours_depense_soumission)
                     AS "Dépense → soumission",
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY jours_soumission_constat)
                     AS "Soumission → constat"
              {delais} GROUP BY pays ORDER BY pays""", JOURS, horizontal=True), 12, PAR_PAYS_HAUTEUR)
    g.ajouter(tableau(
        "Motifs de rejet des pièces",
        f"""SELECT coalesce(motif_rejet, '(sans motif)') AS "Motif", count(*) AS "Pièces"
              FROM bi.pieces WHERE annee = $annee AND {PAR_PAYS} AND etat_code = 'rejected'
             GROUP BY 1 ORDER BY 2 DESC"""), 12, 9)
    g.section("Dossiers à prouver")
    g.ajouter(tableau(
        "Dossiers déclarés avec des lignes sans preuve",
        f"""SELECT numero AS "Dossier", libelle AS "Libellé", pays AS "Pays",
                   libelle_statut AS "Statut", lignes AS "Lignes",
                   lignes_sans_preuve AS "Sans preuve", pieces_incompletes AS "Pièces incomplètes",
                   CASE alerte WHEN 'proof_missing' THEN 'Justificatif manquant'
                               WHEN 'proof_incomplete' THEN 'Justificatif incomplet' ELSE '' END
                     AS "Alerte",
                   date AS "Date"
              FROM bi.dossiers
             WHERE annee = $annee AND {PAR_PAYS} AND (lignes_sans_preuve > 0 OR pieces_incompletes > 0)
               AND statut <> 'draft'
             ORDER BY lignes_sans_preuve DESC"""), 24, 9)
    return tableau_de_bord(
        "bi-justification", "Pilotage — justification et preuves",
        "Ce qui est dépensé contre ce qui est prouvé, l'état des pièces et les délais.",
        g, [ANNEE, PAYS])


def activite():
    g = Grille()
    filtre = f"annee = $annee AND {PAR_PAYS} AND {PAR_TYPE} AND (engagee OR consommee)"
    lignes = f"FROM bi.lignes WHERE {filtre}"
    g.ajouter(stat("Lignes déclarées", f"SELECT count(*) {lignes}"), 6, 4)
    g.ajouter(stat("Montant déclaré", f"SELECT coalesce(sum(montant_xof), 0) {lignes}", FCFA), 6, 4)
    g.ajouter(stat("Montant moyen par ligne", f"SELECT avg(montant_xof) {lignes}", FCFA), 6, 4)
    g.ajouter(stat("Part des 10 premiers bénéficiaires",
                   f"""SELECT bi.ratio(sum(m) FILTER (WHERE rang <= 10), sum(m)) FROM (
                         SELECT sum(montant_xof) AS m,
                                row_number() OVER (ORDER BY sum(montant_xof) DESC NULLS LAST) AS rang
                           {lignes} AND beneficiaire_id IS NOT NULL GROUP BY beneficiaire_id) AS b""",
                   "percentunit", 1,
                   [{"color": "green", "value": None}, {"color": "orange", "value": 0.5},
                    {"color": "red", "value": 0.8}],
                   "Concentration : part du montant qui va aux dix premiers bénéficiaires."),
              6, 4)
    g.ajouter(barres(
        "Montant par mois et par pays",
        f"""SELECT to_char(mois, 'YYYY-MM') AS "Mois", pays, sum(montant_xof) AS montant
              {lignes} GROUP BY mois, pays ORDER BY mois""",
        FCFA, empile=True, pivot=("Mois", "pays", "montant"),
        description="Engagé et consommé, en FCFA, par mois au fuseau de chaque pays."), 24, 10)
    g.ajouter(barres(
        "Par catégorie",
        f"""SELECT coalesce(categorie, '(sans catégorie)') AS "Catégorie",
                   sum(montant_xof) AS "Montant"
              {lignes} GROUP BY 1 ORDER BY 2 DESC NULLS LAST LIMIT 15""", FCFA, horizontal=True),
        12, 10)
    g.ajouter(camembert(
        "Par type de projet",
        f"""SELECT coalesce(type_projet, '(historique)') AS "Type", sum(montant_xof) AS "Montant"
              {lignes} GROUP BY 1 ORDER BY 2 DESC NULLS LAST""", FCFA), 6, 10)
    g.ajouter(camembert(
        "Par mode de paiement",
        f"""SELECT mode_paiement AS "Mode", sum(montant_xof) AS "Montant"
              {lignes} GROUP BY 1 ORDER BY 2 DESC NULLS LAST""", FCFA), 6, 10)
    g.ajouter(tableau(
        "Dix premiers bénéficiaires",
        f"""SELECT beneficiaire AS "Bénéficiaire", type_beneficiaire AS "Type",
                   string_agg(DISTINCT pays, ', ') AS "Pays", count(*) AS "Lignes",
                   sum(montant_xof) AS "Montant",
                   bi.ratio(sum(montant_xof), sum(sum(montant_xof)) OVER ()) AS "Part"
              {lignes} AND beneficiaire_id IS NOT NULL
             GROUP BY beneficiaire_id, beneficiaire, type_beneficiaire
             ORDER BY 5 DESC NULLS LAST LIMIT 10""",
        {"Montant": MONTANT, "Part": ("percentunit", 1, None, None)}), 12, 10)
    g.ajouter(tableau(
        "Comparaison des filiales",
        f"""SELECT pays AS "Pays", count(*) AS "Lignes", sum(montant_xof) AS "Montant",
                   avg(montant_xof) AS "Moyenne par ligne",
                   bi.ratio(sum(montant_xof), sum(sum(montant_xof)) OVER ()) AS "Part",
                   count(DISTINCT dossier_id) AS "Dossiers",
                   count(DISTINCT projet_dossier_id) AS "Projets"
              {lignes} GROUP BY pays ORDER BY 3 DESC NULLS LAST""",
        {"Montant": MONTANT, "Moyenne par ligne": MONTANT, "Part": ("percentunit", 1, None, None)}),
        12, 10)
    g.ajouter(tableau(
        "Par équipe et manager",
        f"""SELECT pays AS "Pays", coalesce(equipe, '(sans équipe)') AS "Équipe",
                   coalesce(manager, '(sans manager)') AS "Manager", count(*) AS "Lignes",
                   sum(montant_xof) AS "Montant", sum(justifie_xof) AS "Justifié"
              {lignes} GROUP BY 1, 2, 3 ORDER BY 5 DESC NULLS LAST""",
        {"Montant": MONTANT, "Justifié": MONTANT}), 12, 10)
    g.ajouter(tableau(
        "Par projet",
        f"""SELECT pays AS "Pays", coalesce(reference_projet_dossier, '') AS "Référence",
                   coalesce(projet_dossier, '(hors projet)') AS "Projet",
                   coalesce(type_projet, '') AS "Type", count(*) AS "Lignes",
                   sum(montant_xof) AS "Montant", sum(justifie_xof) AS "Justifié"
              {lignes} GROUP BY 1, 2, 3, 4 ORDER BY 6 DESC NULLS LAST""",
        {"Montant": MONTANT, "Justifié": MONTANT}), 12, 10)
    return tableau_de_bord(
        "bi-activite", "Pilotage — activité et tendances",
        "Où va l'argent : par mois, catégorie, type de projet, bénéficiaire, filiale.",
        g, [ANNEE, PAYS, TYPE_PROJET])


def controle():
    g = Grille()
    file_ = f"FROM bi.file_controle WHERE {PAR_PAYS}"
    g.ajouter(stat("Lignes à contrôler", f"SELECT count(*) {file_}"), 6, 4)
    g.ajouter(stat("Montant à contrôler", f"SELECT coalesce(sum(montant_xof), 0) {file_}", FCFA),
              6, 4)
    g.ajouter(stat("Attente moyenne", f"SELECT avg(jours_en_attente) {file_}", JOURS, 1,
                   [{"color": "green", "value": None}, {"color": "orange", "value": 15},
                    {"color": "red", "value": 30}]), 6, 4)
    g.ajouter(stat("Plus longue attente", f"SELECT max(jours_en_attente) {file_}", JOURS, 1,
                   [{"color": "green", "value": None}, {"color": "orange", "value": 15},
                    {"color": "red", "value": 30}]), 6, 4)
    g.ajouter(tableau(
        "File de contrôle",
        f"""SELECT numero_dossier AS "Dossier", libelle AS "Ligne", pays AS "Pays",
                   montant AS "Montant", devise AS "Devise", libelle_statut AS "Statut",
                   soumise_le AS "Soumise le", jours_en_attente AS "Attente (j)",
                   CASE WHEN a_preuve THEN 'Oui' ELSE 'Non' END AS "Pièce",
                   manager AS "Manager"
              {file_} ORDER BY jours_en_attente DESC NULLS LAST""",
        {"Montant": DEVISE,
         "Attente (j)": (None, 1, [{"color": "green", "value": None},
                                   {"color": "orange", "value": 15},
                                   {"color": "red", "value": 30}], "color-text")}),
        16, 11)
    g.ajouter(barres(
        "Ancienneté de la file",
        f"""SELECT tr.libelle AS "Ancienneté", count(f.ligne_id) AS "Lignes"
              FROM (VALUES (1, '0 à 7 jours', 0, 7), (2, '8 à 30 jours', 7, 30),
                           (3, '31 à 90 jours', 30, 90), (4, 'Plus de 90 jours', 90, NULL),
                           (5, 'Soumission non tracée', NULL, NULL))
                   AS tr(rang, libelle, apres, jusqu_a)
              LEFT JOIN (SELECT ligne_id, jours_en_attente {file_}) AS f
                ON CASE WHEN tr.rang = 5 THEN f.jours_en_attente IS NULL
                        ELSE f.jours_en_attente > tr.apres - CASE WHEN tr.rang = 1 THEN 1 ELSE 0 END
                         AND (tr.jusqu_a IS NULL OR f.jours_en_attente <= tr.jusqu_a) END
             GROUP BY tr.rang, tr.libelle ORDER BY tr.rang"""), 8, 11)
    g.section("Décisions de l'exercice")
    decisions = f"FROM bi.delais WHERE annee = $annee AND {PAR_PAYS}"
    g.ajouter(barres(
        "Constats par mois",
        f"""SELECT to_char(date_trunc('month', constatee_le), 'YYYY-MM') AS "Mois",
                   count(*) FILTER (WHERE statut IN ('justified', 'closed')) AS "Justifiées",
                   count(*) FILTER (WHERE statut = 'unjustified') AS "Non justifiées"
              {decisions} AND constatee_le IS NOT NULL GROUP BY 1 ORDER BY 1""", empile=True),
        12, 9)
    g.ajouter(barres(
        "Délai médian de constat par mois (jours)",
        f"""SELECT to_char(date_trunc('month', constatee_le), 'YYYY-MM') AS "Mois",
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY jours_soumission_constat)
                     AS "Soumission → constat"
              {decisions} AND constatee_le IS NOT NULL GROUP BY 1 ORDER BY 1""", JOURS), 12, 9)
    g.ajouter(stat("Non justifiées", f"SELECT count(*) {decisions} AND statut = 'unjustified'"),
              6, 4)
    g.ajouter(stat("Réouvertures", f"SELECT coalesce(sum(reouvertures), 0) {decisions}"), 6, 4)
    g.ajouter(stat("Rectifications en attente",
                   f"SELECT count(*) FROM bi.rectifications WHERE {PAR_PAYS} AND etat = 'pending'",
                   seuils=[{"color": "green", "value": None}, {"color": "orange", "value": 1}]),
              6, 4)
    g.ajouter(stat("Décision de rectification (médiane)",
                   f"SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY jours_de_decision) "
                   f"FROM bi.rectifications WHERE annee = $annee AND {PAR_PAYS}", JOURS, 1), 6, 4)
    g.ajouter(tableau(
        "Rectifications",
        f"""SELECT demandee_le AS "Demandée le", pays AS "Pays", ligne_id AS "Ligne",
                   libelle_etat AS "État", demandee_par AS "Par", decidee_par AS "Décidée par",
                   jours_de_decision AS "Délai (j)", montant AS "Montant", devise AS "Devise"
              FROM bi.rectifications WHERE annee = $annee AND {PAR_PAYS}
             ORDER BY demandee_le DESC"""), 24, 9)
    return tableau_de_bord(
        "bi-controle", "Pilotage — contrôle",
        "La file de la RH, son ancienneté, et les décisions de l'exercice.",
        g, [ANNEE, PAYS])


def anomalies():
    g = Grille()
    g.ajouter(tableau(
        "Dépenses inhabituelles",
        f"""SELECT jour AS "Date", pays AS "Pays", numero_dossier AS "Dossier", libelle AS "Ligne",
                   montant AS "Montant", devise AS "Devise", bi.arrondi(seuil, 0) AS "Seuil",
                   libelle_statut AS "Statut", manager AS "Manager", beneficiaire AS "Bénéficiaire"
              FROM bi.inhabituelles WHERE annee = $annee AND {PAR_PAYS} ORDER BY montant DESC""",
        description="Plus de « facteur » fois la moyenne des autres dépenses du pays et de "
                    "l'exercice (facteur réglé dans Configuration › Général)."), 24, 9)
    g.ajouter(tableau(
        "Doublons probables",
        f"""SELECT jour AS "Date", pays AS "Pays", reference AS "Bénéficiaire ou libellé",
                   montant AS "Montant", devise AS "Devise", lignes AS "Lignes",
                   array_to_string(dossiers, ', ') AS "Dossiers"
              FROM bi.doublons WHERE annee = $annee AND {PAR_PAYS} ORDER BY jour DESC""",
        description="Même jour, même montant, même bénéficiaire (ou même libellé) : à vérifier."),
        12, 9)
    g.ajouter(tableau(
        "Dépenses du week-end",
        f"""SELECT jour AS "Date", pays AS "Pays", numero_dossier AS "Dossier", libelle AS "Ligne",
                   montant AS "Montant", devise AS "Devise", mode_paiement AS "Paiement"
              FROM bi.lignes WHERE annee = $annee AND {PAR_PAYS} AND NOT brouillon
               AND jour_semaine IN (6, 7) ORDER BY jour DESC""",
        description="Samedi et dimanche, à l'heure du pays."), 12, 9)
    g.section("Devises")
    g.ajouter(stat("Devises sans taux",
                   "SELECT coalesce(nullif(array_to_string(devises_non_converties, ', '), ''), "
                   "'Aucune') FROM bi.consolidation WHERE annee = $annee", texte=True), 8, 4)
    g.ajouter(stat("Lignes payées dans une autre devise",
                   f"SELECT count(*) FROM bi.lignes WHERE annee = $annee AND {PAR_PAYS} "
                   "AND NOT brouillon AND devise_origine IS NOT NULL"), 8, 4)
    g.ajouter(tableau(
        "Paiements en devise étrangère",
        f"""SELECT devise_origine AS "Devise payée", pays AS "Pays", count(*) AS "Lignes",
                   sum(montant_origine) AS "Montant payé", sum(montant) AS "Montant imputé"
              FROM bi.lignes WHERE annee = $annee AND {PAR_PAYS} AND NOT brouillon
               AND devise_origine IS NOT NULL GROUP BY 1, 2 ORDER BY 3 DESC"""), 8, 8)
    g.section("Traçabilité")
    g.ajouter(barres(
        "Actions sensibles par jour",
        f"""SELECT to_char(jour, 'YYYY-MM-DD') AS "Jour", libelle_action, count(*) AS n
              FROM bi.journal WHERE sensible AND extract(year FROM le) = $annee
               AND (pays_id IS NULL OR {PAR_PAYS}) GROUP BY jour, libelle_action ORDER BY jour""",
        empile=True, pivot=("Jour", "libelle_action", "n"),
        description="Réouvertures, rectifications, suppressions, refus, imports, corbeille."),
        12, 9)
    g.ajouter(tableau(
        "Sorties de données (téléchargements et exports)",
        """SELECT compte AS "Compte", count(*) AS "Sorties", max(le) AS "Dernière"
             FROM bi.journal WHERE action = 'downloaded' AND extract(year FROM le) = $annee
            GROUP BY compte ORDER BY 2 DESC"""), 12, 9)
    g.ajouter(tableau(
        "Dernières actions sensibles",
        f"""SELECT le AS "Le", compte AS "Compte", libelle_action AS "Action",
                   type_objet AS "Objet", libelle AS "Libellé", pays AS "Pays"
              FROM bi.journal WHERE sensible AND extract(year FROM le) = $annee
               AND (pays_id IS NULL OR {PAR_PAYS}) ORDER BY le DESC LIMIT 100"""), 24, 9)
    g.section("Comptes et adoption")
    g.ajouter(stat("Comptes actifs", "SELECT count(*) FROM bi.comptes WHERE actif"), 6, 4)
    g.ajouter(stat("Double authentification",
                   "SELECT bi.ratio(count(*) FILTER (WHERE double_authentification), count(*)) "
                   "FROM bi.comptes WHERE actif", "percentunit", 0,
                   [{"color": "red", "value": None}, {"color": "orange", "value": 0.5},
                    {"color": "green", "value": 1}]), 6, 4)
    g.ajouter(stat("Sans connexion depuis 30 jours",
                   "SELECT count(*) FROM bi.comptes WHERE actif AND "
                   "(derniere_connexion IS NULL OR derniere_connexion < now() - interval '30 days')"),
              6, 4)
    g.ajouter(stat("Mot de passe provisoire",
                   "SELECT count(*) FROM bi.comptes WHERE actif AND mot_de_passe_provisoire"), 6, 4)
    g.ajouter(tableau(
        "Comptes",
        """SELECT compte AS "Compte", libelle_role AS "Rôle",
                  coalesce(array_to_string(pays, ', '), 'Tous') AS "Pays",
                  CASE WHEN actif THEN 'Oui' ELSE 'Non' END AS "Actif",
                  CASE WHEN double_authentification THEN 'Oui' ELSE 'Non' END AS "2FA",
                  derniere_connexion AS "Dernière connexion", actions_30_jours AS "Actions (30 j)"
             FROM bi.comptes ORDER BY actif DESC, libelle_role, compte"""), 16, 9)
    g.ajouter(tableau(
        "Corbeille (avant l'ouverture)",
        f"""SELECT supprime_le AS "Le", nature AS "Nature", reference AS "Référence",
                   libelle AS "Libellé", pays AS "Pays", supprime_par AS "Par", motif AS "Motif"
              FROM bi.corbeille WHERE element_choisi AND (pays_id IS NULL OR {PAR_PAYS})
             ORDER BY supprime_le DESC"""), 8, 9)
    return tableau_de_bord(
        "bi-anomalies", "Pilotage — anomalies et traçabilité",
        "Ce qui sort de la norme, ce qui sort du système, et qui se sert de la plateforme.",
        g, [ANNEE, PAYS])


TABLEAUX = {
    "vue-d-ensemble.json": vue_d_ensemble,
    "enveloppes.json": enveloppes,
    "justification.json": justification,
    "activite.json": activite,
    "controle.json": controle,
    "anomalies.json": anomalies,
}


def rendus():
    return {
        nom: json.dumps(fabrique(), ensure_ascii=False, indent=2) + "\n"
        for nom, fabrique in TABLEAUX.items()
    }


def main(arguments):
    attendus = rendus()
    if "--verifier" in arguments:
        ecarts = [
            nom for nom, contenu in attendus.items()
            if not (DOSSIER / nom).exists()
            or (DOSSIER / nom).read_text(encoding="utf-8") != contenu
        ]
        if ecarts:
            print("Tableaux à régénérer :", ", ".join(ecarts), file=sys.stderr)
            return 1
        return 0
    DOSSIER.mkdir(parents=True, exist_ok=True)
    for nom, contenu in attendus.items():
        (DOSSIER / nom).write_text(contenu, encoding="utf-8")
        print(f"écrit {DOSSIER / nom}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
