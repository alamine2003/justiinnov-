# Modèle de données — Suivi budgétaire

> Document de référence du modèle de données pour la transformation du suivi
> budgétaire Excel en application centralisée. Ce document **fige les décisions
> de modélisation** et sert de socle aux migrations, à l'API REST et au
> frontend. Il est aligné sur le cahier des charges (vision, référence Excel,
> périmètre 5.1 et au-delà).

## 1. Rappel des objectifs

- Attribuer une **enveloppe annuelle par pays** (DOO).
- Suivre en temps réel et de façon **traçable** l'utilisation de l'enveloppe
  par les managers et équipes.
- Relier chaque dépense à son contexte : **date/heure, pays, utilisateur, lieu,
  montant, intitulé/projet, prospect ou bénéficiaire, statut de validation et
  preuve documentaire** (PDF, reçu, décharge, facture ou autre livrable).
- Conserver l'historique des changements (audit).

### Correspondance avec le fichier Excel « BASE DE DONNEES ACTIONS »

| Colonne Excel       | Modèle                       | Notes |
|---------------------|------------------------------|-------|
| N°ORDRE             | `Dossier.number`             | devient une entité regroupant les preuves |
| DATE                | `Expense.date` / `Dossier.date` | |
| TEAM                | `Expense.team`               | dupliqué sur chaque ligne |
| OWNER               | `Expense.owner`              | manager propriétaire |
| LIBELLE DES TRANSACTIONS | `Expense.title`          | |
| DÉPENSES            | `Expense.amount`             | |
| MONTANT JUSTIFIER   | `Expense.justified_amount`   | |
| ÉCART               | *calculé* = amount − justified_amount | non stocké |
| PIÈCES JUSTIFICATIVES | `Proof` (rattachées au Dossier) | |

> **Interprétation `N°ORDRE`** : le numéro d'ordre devient une entité
> « Dossier de justification » regroupant les preuves associées à une même
> opération/dépense. Les lignes Excel deviennent des lignes de dépenses
> rattachées à ce dossier.

## 2. Entités du référentiel (existantes, réutilisées)

Déjà implémentées en 5.1 et réutilisées sans modification :

- `Country` — pays (devise, fuseau horaire, managers M2M, actif/inactif)
- `Manager` — responsable commercial / de pays
- `Team` — équipe rattachée à un pays
- `CostCenter` — centre de coûts rattaché à un pays
- `Project` — projet avec `status` et `budget`
- `ExpenseTitle` — intitulé de dépenses rattaché à un pays
- `MarketingCategory` — catégorie marketing
- `ChangeLog` — journal des changements (création, mise à jour, rattachement,
  activation/désactivation)

## 3. Nouvelles entités (cœur du suivi budgétaire)

### 3.1 `Budget` — enveloppe budgétaire

Enveloppe annuelle par pays, déclinable en **sous-enveloppes par projet**.

| Champ | Type | Notes |
|-------|------|-------|
| `country`   | FK → Country | requis |
| `year`      | Integer      | |
| `project`   | FK → Project (null=True, blank=True) | **sous-enveloppe** si renseigné ; sinon enveloppe globale du pays |
| `amount`    | Decimal(14,2) | montant de l'enveloppe |
| `is_active` | Bool | défaut True |
| `created_at` / `updated_at` | DateTime | hérité de `TimeStampedModel` |

Contraintes d'unicité :
- `(country, year)` enveloppe globale (project null).
- `(country, project, year)` sous-enveloppe.

Champs **calculés** (non stockés) :
- `consumed` — somme des `amount` des dépenses liées
- `justified` — somme des `justified_amount`
- `gap` — `consumed − justified`
- `remaining` — `amount − consumed`
- `justification_rate` — `justified / consumed` (si consumed ≠ 0)

### 3.2 `Beneficiary` — prospect / bénéficiaire

Entité **dédiée et typée**, couvrant « prospect ou bénéficiaire ».

| Champ | Type | Notes |
|-------|------|-------|
| `name`      | Char(180) | unique |
| `type`      | Char(32)  | choix : prospect / client / fournisseur / bénéficiaire / autre |
| `contact`   | Char(180) | optionnel |
| `is_active` | Bool | défaut True |
| `created_at` / `updated_at` | DateTime | |

### 3.3 `Dossier` — le « N°ORDRE »

Regroupe les preuves et regroupe les lignes de dépenses d'une même opération.

| Champ | Type | Notes |
|-------|------|-------|
| `number` | Char(50) | **N°ORDRE**, unique, auto-généré ou saisi |
| `label`  | Char(250) | description du dossier |
| `country` | FK → Country | |
| `team`   | FK → Team (null) | contexte du dossier |
| `owner`  | FK → Manager (null) | responsable du dossier |
| `date`   | DateField | date du dossier |
| `status` | Char(20)  | **workflow complet** (voir 3.6) |
| `note`   | TextField (blank) | remarque de contrôle |
| `created_at` / `updated_at` | DateTime | |

> Le contexte (country/team/owner/date) est porté au niveau **Dossier**, mais
> chaque ligne de dépense **duplique** ces informations pour une traçabilité
> ligne par ligne indépendante.

### 3.4 `Expense` — ligne de dépense (une ligne Excel)

Contexte **dupliqué sur chaque ligne**.

| Champ | Type | Notes |
|-------|------|-------|
| `dossier`         | FK → Dossier | ligne rattachée au dossier (N°ORDRE) |
| `country`         | FK → Country | dupliqué |
| `team`            | FK → Team | dupliqué |
| `owner`           | FK → Manager | dupliqué |
| `date`            | DateTime | |
| `place`           | Char(180) | lieu |
| `title`           | Char(250) | LIBELLE DES TRANSACTIONS |
| `project`         | FK → Project (null) | |
| `expense_title`   | FK → ExpenseTitle (null) | intitulé |
| `beneficiary`     | FK → Beneficiary (null) | prospect/bénéficiaire |
| `amount`          | Decimal(14,2) | DÉPENSES |
| `justified_amount`| Decimal(14,2) | MONTANT JUSTIFIER, défaut 0 |
| `status`          | Char(20) | **workflow complet** (voir 3.6) |
| `note`            | TextField (blank) | |
| `created_at` / `updated_at` | DateTime | |

Champs **calculés** (non stockés) :
- `gap` — `amount − justified_amount`

> **Écart** : toujours calculé, jamais saisi (décision validée).

### 3.5 `Proof` — pièce justificative (rattachée au Dossier)

Les preuves sont rattachées au **Dossier** (logique d'ensemble documentaire du
N°ORDRE).

| Champ | Type | Notes |
|-------|------|-------|
| `dossier`     | FK → Dossier | preuve de l'ensemble documentaire |
| `file`        | FileField   | PDF, image, reçu, facture, décharge, livrable |
| `type`        | Char(50)    | Reçu / Facture / Décharge / Livrable / Autre… |
| `is_complete` | Bool        | drapeau « justificatif incomplet » |
| `uploaded_by` | FK → user (null) | |
| `uploaded_at` | DateTime (auto_now_add) | |

### 3.6 Workflow de validation

**Workflow complet sur le Dossier ET sur chaque ligne** (décision validée).

États possibles (choix partagés) :

```
brouillon → soumis → en contrôle → validé / refusé
```

- `Dossier.status` — statut principal du dossier.
- `Expense.status` — statut de chaque ligne.

Toute transition est journalisée dans `ChangeLog` (et/ou `AuditLog`) avec le
validateur, le commentaire et l'horodatage.

### 3.7 `AuditLog` — journal d'audit des actions sensibles

Extension de l'audit au-delà du `ChangeLog` existant (dépenses, validations,
uploads de justificatifs, actions de gestion).

| Champ | Type | Notes |
|-------|------|-------|
| `user`       | FK → user (null) | auteur |
| `action`     | Char | type d'action sensible |
| `object`     | Char / generic | cible (dossier, dépense…) |
| `detail`     | JSON | données de l'action |
| `created_at` | DateTime | |

---

## 4. Relations (synthèse)

```
Country 1─* Budget
Country 1─* Dossier
Country 1─* Expense
Country 1─* Beneficiary            (via référence)

Dossier 1─* Expense
Dossier 1─* Proof
Dossier *─1 Team   (nullable, dupliqué)
Dossier *─1 Manager (owner, nullable)

Budget *─1 Project (nullable -> sous-enveloppe)
Expense *─1 Project        (nullable)
Expense *─1 ExpenseTitle   (nullable)
Expense *─1 Beneficiary    (nullable)
Expense *─1 Manager (owner, dupliqué)
Expense *─1 Team   (dupliqué)

Budget   ==> champs calculés : consumed / justified / gap / remaining / justification_rate
Expense  ==> champ calculé  : gap = amount − justified_amount
```

## 5. Décisions de modélisation validées

| # | Décision | Choix |
|---|----------|-------|
| 1 | Contexte (country/team/owner/date) | **Dupliqué sur chaque ligne de dépense** |
| 2 | ÉCART | **Calculé** = amount − justified_amount |
| 3 | Pièces justificatives | **Au niveau Dossier** |
| 4 | Workflow | **Complet** sur Dossier et sur lignes |
| 5 | Prospect / bénéficiaire | **Entité `Beneficiary` dédiée et typée** |
| 6 | Enveloppe | **Par pays/année + sous-enveloppes par projet** |

## 6. Inspirations Excel à conserver

- `N°ORDRE` = `Dossier.number`.
- « Reçu (justif incomplet) » → `Proof.is_complete = False`.
- Les agrégats `Dépenses totales`, `Montant justifié`, `Écart` sont des
  **sommes calculées** sur les `Expense` (et consommées par les tableaux de
  bord / exports).

## 7. Points techniques à prévoir (implémentation)

- `MEDIA_URL` / `MEDIA_ROOT` dans `settings.py` + servir les fichiers (uploads
  de preuves).
- Nouvelles migrations pour `Budget`, `Beneficiary`, `Dossier`, `Expense`,
  `Proof`, `Validation/status`, éventuellement `AuditLog`.
- Étendre le `ChangeLog` (ou `AuditLog`) aux dépenses et aux validations.
- API REST : endpoints CRUD + agrégats de suivi budgétaire + workflow.
- Frontend : saisie des dépenses, dossiers, upload de preuves, tableaux de
  bord, exports Excel/PDF.
