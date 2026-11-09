# Revue d'architecture — novembre 2026 (version 2.4.1)

Revue du 9 novembre 2026, sur `main` 3daf4b1 (version 2.4.0). Elle confronte
le code aux cinq principes SOLID et inventorie chaque requête qui filtre,
trie ou joint face aux index posés en base. Les décisions qui en sortent sont
la **123** (carte des index) et la **124** (SOLID) de
[`model-de-donnees.md`](model-de-donnees.md) ; ce fichier tient la liste
complète des écarts, pour qu'aucun ne se perde.

Verdict d'ensemble : un **monolithe modulaire** sain — un backend Django,
six applications dans un ordre de dépendance vérifié par un test, une base
PostgreSQL. Il convient à une équipe d'une personne et à des règles qui
exigent des transactions ; il est à garder tel quel, sans découpage en
services.

## Déjà solide

- Le circuit est décrit par des tables (`expenses/workflow.py` :
  `TRANSITIONS`, `ACTION_CAPACITES`, `PROOF_TRANSITIONS`) et exécuté par un
  tronc commun qui choisit sa stratégie (`transitions._CIRCUITS`).
- Les droits sont un registre de capacités nommées (`accounts/permissions.py`),
  réglables sans toucher au code ; une vue déclare une capacité, jamais un rôle.
- Les services ignorent le HTTP : ils lèvent les refus de `core/regles.py`
  et reçoivent une `Trace` (`core/journal.py`).
- Les exports passent par un registre de formats (`reporting/exports.py`).
- L'ordre des applications est gardé par `core/tests/test_dependances.py`.

## Les 24 écarts

État : **corrigé** dans la 2.4.1 (sans changement de comportement : schéma
d'API identique, suites vertes), ou **à faire**, avec sa priorité.

| N° | Principe | Écart | Où | État |
|---|---|---|---|---|
| 1 | D | La vue de dépôt connaissait le client S3 | `expenses/views.py` | corrigé : `stockage.PANNES_DE_STOCKAGE` |
| 2 | S | Le tableau de bord additionnait des devises différentes, puis jetait le résultat | `reporting/views.py` | corrigé |
| 3 | O | La liste des formats d'export était recopiée dans les routes | `reporting/urls.py` | corrigé : `tuple(exports.FORMATS)` |
| 4 | D | Devise de consolidation écrite en dur (serveur et interface) | `reporting/views.py`, `pages/dashboard/index.tsx` | corrigé |
| 5 | D/S | Le contrôle de périmètre d'un objet chargé était réécrit dans trois services (décision 39) | `expenses/transitions.py`, `expenses/corbeille.py`, `budget/transitions.py` | corrigé : `accounts.perimetre.exiger_dans_le_perimetre` |
| 6 | L | `BackOfficePermission` ignorait la capacité déclarée par sa vue | `accounts/views.py` | corrigé |
| 7 | L/I | `DossierViewSet` hérite d'une création qu'il refuse (405), et le sérialiseur garde une branche de création morte | `expenses/views.py`, `expenses/serializers.py` | à faire (3) — régénère le schéma d'API |
| 8 | S | Le dépôt d'une pièce est un service caché dans la vue (décision 41) | `ProofViewSet.perform_create/update` | à faire (1) — garder l'ordre des verrous |
| 9 | S | La saisie d'une ligne est orchestrée dans la vue (décision 41) | `ExpenseViewSet.perform_create/update` | à faire (1) |
| 10 | D | `accounts` importe `expenses` dans quatre fonctions de `ProjectViewSet` (décision 40) ; le test d'ordre ne compte pas ces imports | `accounts/referentiel.py` | à faire (2) |
| 11 | S/O | La règle « motif obligatoire » était copiée six fois | `core/serializers.py`, `accounts/referentiel.py` | corrigé : `MotifExigeMixin` |
| 12 | S | `importer_depenses` fait tout en 210 lignes | `reporting/imports.py` | à faire (3) — ne pas sortir de la boucle les contrôles du dossier |
| 13 | S | Conversion de devise, équipe de la ligne et auteur du brouillon recopiés entre sérialiseur et import | `expenses/serializers.py`, `reporting/imports.py` | à faire (3) |
| 14 | S/O | La reconnaissance du contenu des pièces vivait dans les sérialiseurs, un `if` par format | `expenses/serializers.py` | corrigé : `expenses/contenu.py`, table `FORMATS` |
| 15 | S | L'état de la double authentification est modifié dans quatre vues | `accounts/views.py` | à faire (4) |
| 16 | S | L'enregistrement de la matrice des droits est dans la vue | `accounts/views.py` | à faire (4) |
| 17 | S | Les agrégats du pilotage sont calculés dans les vues | `reporting/views.py` | à faire (4) |
| 18 | O | Les actions du circuit étaient une chaîne de `if` | `expenses/transitions.executer` | corrigé : `_SERVICES` |
| 19 | S | `transitions.py` réunit cinq sujets en 1 287 lignes | `expenses/transitions.py` | à garder pour l'instant : des tests le patchent comme module ; réexporter si on découpe |
| 20 | S | Le motif « enregistrer » est recopié 29 fois dans l'interface | `frontend/src` | à faire (5) |
| 21 | I/D | `ProofPanel` lit les règles de dépôt sur une API d'administration qu'aucun déposant n'atteint | `components/expenses/proof-panel.tsx` | **décision de la direction** : exposer ces règles au déposant, ou retirer la branche |
| 22 | S | Le formulaire des comptes porte 13 états et construit sa charge utile | `pages/configuration/users-section.tsx` | à faire (5) |
| 23 | S | La fiche dossier orchestre elle-même ses mutations | `pages/dossiers/detail.tsx` | à faire (5) |
| 24 | S/O | Un drapeau `compact` cache deux composants ; la configuration recopie ses onglets | `proof-panel.tsx`, `pages/configuration/index.tsx` | à faire (5) — captures à repasser |

Priorités : (1) les règles qui vivent encore dans des vues, qu'un import ou
une commande contourneraient ; (2) la dépendance à rebours d'`accounts` ;
(3) les duplications du backend ; (4) les extractions locales ; (5)
l'interface.

## Index

Voir la décision 123 : mesures avant et après, index ajouté et index écartés,
et la carte `backend/config/tests/test_index.py` qui garde l'ensemble.
