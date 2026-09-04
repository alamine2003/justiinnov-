# Modèle de données — Suivi budgétaire

> Document de référence du modèle de données, **tenu à jour avec le code** :
> ce qui est écrit ici correspond aux modèles Django (`backend/*/models.py`)
> et à leurs migrations. Il fige les décisions de modélisation (section 5) et
> sert de socle à l'API REST et au frontend. Une entité qui change se met à
> jour ici dans le même commit. Les éléments marqués **(en cours)** sont
> présents dans le code mais encore en cours de stabilisation.

## 1. Rappel des objectifs

- Attribuer une **enveloppe annuelle par pays** (direction des opérations).
- Suivre en temps réel et de façon **traçable** l'utilisation de l'enveloppe
  par les managers et équipes.
- Relier chaque dépense à son contexte : **date/heure, pays, utilisateur, lieu,
  montant, intitulé/projet, prospect ou bénéficiaire, statut de justification
  et preuve documentaire** (PDF, reçu, décharge, facture ou autre livrable).
- Conserver l'historique des changements (audit).

Le but n'est pas d'autoriser des dépenses : c'est de savoir **ce qui a été
dépensé, quand, où, au profit de qui — et où est la preuve**. D'où
« justifié » plutôt que « validé ».

### Correspondance avec le fichier Excel « BASE DE DONNEES ACTIONS »

L'export `/api/exports/expenses.xlsx` reprend les colonnes d'origine, et
l'import `/api/imports/expenses.xlsx` lit exactement ce format (13 colonnes).

| Colonne Excel | Modèle | Notes |
|---|---|---|
| N°ORDRE | `Dossier.number` | entité regroupant lignes et preuves |
| DATE | `Expense.date` | date et heure, lues dans le fuseau du pays |
| PAYS | `Expense.country` | ajoutée : le fichier d'origine était mono-pays |
| TEAM | `Expense.team` | dupliqué sur chaque ligne |
| OWNER | `Expense.owner` | manager propriétaire |
| LIBELLE DES TRANSACTIONS | `Expense.title` | |
| DEPENSES | `Expense.amount` | dans la devise du pays |
| DEVISE D'ORIGINE | `Expense.original_currency` | vide si décaissée dans la devise du pays |
| MONTANT D'ORIGINE | `Expense.original_amount` | tel qu'il figure sur la pièce |
| MONTANT JUSTIFIER | `Expense.justified_amount` | |
| ECART | *calculé* = `amount − justified_amount` | jamais stocké |
| STATUT | `Expense.status` | |
| PIECES JUSTIFICATIVES | `Proof` (rattachées au dossier) | noms et état des pièces |

> **Interprétation `N°ORDRE`** : le numéro d'ordre devient une entité
> « dossier de justification » regroupant les preuves associées à une même
> opération. Les lignes Excel deviennent des lignes de dépenses rattachées à
> ce dossier.

## 2. Référentiel (`core`)

Toutes ces entités héritent de `TimeStampedModel` (`created_at`,
`updated_at`) et se retirent par **désactivation** (`is_active`), jamais par
suppression : l'API répond 405 sur `DELETE`.

- `Country` — pays : `country_ref` (identifiant fonctionnel, ex. `TG-01`),
  `name`, `code` ISO validé contre la liste des pays d'Afrique
  (`core/africa.py`), `currency`, `currency_symbol`, `timezone`, `managers`
  (M2M), `is_active`.
- `Manager` — responsable ; peut exister sans compte utilisateur.
- `Team`, `CostCenter` (`code` unique par pays), `Project` (`status`,
  `budget`), `ExpenseTitle` (`label` unique par pays), `MarketingCategory`
  (`name` unique par pays) — tous rattachés à un pays.
- `ChangeLog` — journal des changements du référentiel et des budgets :
  `model_name`, `object_id`, `label`, `action` (création, mise à jour,
  changement de rattachement, désactivation, réactivation, suppression,
  réinitialisation et changement de mot de passe, connexion, échec de
  connexion, déconnexion), `from_value` / `to_value`, `changed_fields`,
  `performed_by`, `ip_address`, `created_at`. Les suppressions faites hors
  API (admin, shell) y sont journalisées, cascades comprises.
- `WorkflowConfiguration` — **singleton** (pk = 1, mis en cache, non
  supprimable) qui porte la politique du circuit, modifiable par le siège via
  `/api/workflow-configuration/` : `require_review_step` (étape « en
  contrôle » obligatoire), `unjustified_alert_days`, `alert_thresholds`
  (JSON, ex. `[80, 90, 100]`), `unusual_expense_factor`,
  `default_overrun_policy` (`block` / `warn` / `approval`),
  `warn_without_proof_submission`. Les variables d'environnement
  `ALERT_THRESHOLDS`, `UNUSUAL_EXPENSE_FACTOR`, `UNJUSTIFIED_ALERT_DAYS` et
  `WARN_WITHOUT_PROOF_SUBMISSION` n'en donnent que les valeurs initiales.

## 3. Comptes et périmètres (`accounts`)

### `UserProfile`

Un par compte Django (`OneToOne`, `related_name="profile"`). **Un compte
sans profil est refusé par l'API.**

| Champ | Type | Notes |
|---|---|---|
| `role` | Char(32) | `super_admin`, `admin`, `doo`, `country_manager`, `owner`, `controller`, `auditor` |
| `countries` | M2M → Country | périmètre ; vide pour un rôle du siège = tous les pays. Un rôle pays sans périmètre ne voit **rien** |
| `teams` | M2M → Team | équipes du compte |
| `manager` | FK → Manager (null) | le manager du référentiel que ce compte incarne |
| `must_change_password` | Bool | mot de passe provisoire : la plateforme reste fermée tant qu'il n'est pas remplacé |

Les rôles du siège (`super_admin`, `admin`, `doo`, `controller`, `auditor`)
constatent ; les rôles pays (`country_manager`, `owner`) déclarent. Un
responsable pays ne justifie jamais une dépense, et celui qui a saisi une
dépense ne la justifie pas lui-même, fût-il au siège. Les identités
(`created_by`, `uploaded_by`, `requested_by`, `performed_by`, `user` du
journal d'audit) sont stockées **en texte** (nom d'utilisateur), pas en clé
étrangère : une trace survit à la désactivation ou au renommage du compte.

## 4. Budget (`budget`)

### 4.1 `Budget` — enveloppe et sous-enveloppes

Enveloppe annuelle par pays, déclinable en sous-enveloppes selon **une**
dimension à la fois : un projet, une équipe **ou** un manager.

| Champ | Type | Notes |
|---|---|---|
| `country` | FK → Country | requis |
| `year` | Integer | |
| `project` | FK → Project (null) | sous-enveloppe par projet |
| `team` | FK → Team (null) | sous-enveloppe par équipe |
| `manager` | FK → Manager (null) | sous-enveloppe par manager |
| `amount` | Decimal(16,2) ≥ 0 | montant, dans la devise du pays |
| `overrun_policy` | Char(20) | `block` (refuser la justification au-delà), `warn` (alerter), `approval` (réserver la justification à la direction des opérations) ; défaut lu dans `WorkflowConfiguration` |
| `is_active` | Bool | |

Contraintes en base :

- `unique_enveloppe_pays_annee` — une seule enveloppe globale par
  `(country, year)` (les trois dimensions nulles) ;
- `unique_sous_enveloppe_projet_annee` — `(country, project, year)` ;
- `unique_sous_enveloppe_equipe_annee` — `(country, team, year)` ;
- `unique_sous_enveloppe_manager_annee` — `(country, manager, year)` ;
- `sous_enveloppe_une_seule_dimension` (CheckConstraint) — au plus une des
  trois dimensions renseignée.

Une sous-enveloppe **découpe** l'enveloppe du pays : la consolidation ne
l'additionne pas. Une dépense s'impute sur la plus précise qui la concerne —
projet, puis équipe, puis manager — et à défaut sur l'enveloppe du pays ;
le résultat est figé dans `Expense.budget`.

Champs **calculés** côté serveur (`budget/aggregates.py`), jamais stockés ni
recalculés par l'interface :

- `engaged` (**engagé**) — lignes soumises ou en contrôle ;
- `consumed` (**consommé**) — lignes justifiées, non justifiées ou
  clôturées : une dépense non justifiée pèse quand même ;
- `justified` — somme des `justified_amount` ;
- `gap` — `consumed − justified`, le chiffre que l'application existe pour
  faire diminuer ;
- `remaining` — `amount − consumed − engaged` ;
- `justification_rate` — `justified / consumed` si `consumed ≠ 0`.

La consolidation au siège se fait en FCFA au taux en vigueur à la date de
l'opération ; une devise sans taux est **exclue du total et signalée**.

### 4.2 `BudgetReallocation` — transfert entre enveloppes

| Champ | Type | Notes |
|---|---|---|
| `source` / `target` | FK → Budget | |
| `amount` | Decimal(16,2) > 0 | |
| `reason` | Text | obligatoire |
| `status` | Char | `pending`, `approved`, `rejected` |
| `requested_by` | Char(180) | identité en texte |

`approve` exécute le transfert (montants mis à jour, entrée `ChangeLog`) ;
`reject` exige un motif.

### 4.3 `ExchangeRate` — taux de conversion

| Champ | Type | Notes |
|---|---|---|
| `currency` | Char(3) | ISO 4217 |
| `rate_to_xof` | Decimal | nombre de FCFA pour une unité |
| `valid_from` | Date | unique par `(currency, valid_from)` |

Le taux appliqué à une dépense en devise étrangère est **figé** sur la ligne
(`Expense.original_rate`) : corriger la table ne réécrit pas l'histoire.

## 5. Dépenses et justification (`expenses`)

### 5.1 `Beneficiary` — prospect / bénéficiaire

Entité **typée et cloisonnée par pays** : un pays ne lit pas les
fournisseurs ni les prospects d'un autre.

| Champ | Type | Notes |
|---|---|---|
| `country` | FK → Country | |
| `name` | Char(180) | **unique par pays** (`unique_beneficiaire_par_pays`) |
| `kind` | Char(32) | `prospect`, `client`, `supplier`, `beneficiary`, `other` |
| `contact` | Char(180) | optionnel |
| `is_active` | Bool | |

### 5.2 `Dossier` — le « N°ORDRE »

Regroupe les lignes de dépenses d'une même opération et les preuves qui les
appuient.

| Champ | Type | Notes |
|---|---|---|
| `number` | Char(50) | **N°ORDRE**, unique, auto-généré ou saisi |
| `label` | Char(250) | |
| `country` | FK → Country (PROTECT) | |
| `team` | FK → Team (null) | contexte |
| `owner` | FK → Manager (null) | responsable |
| `date` | Date | |
| `status` | Char(20) | circuit (5.5) |
| `note` | Text | remarque de contrôle |
| `created_by` | Char(180) | **(en cours)** — identité en texte de qui a ouvert le dossier : celui qui l'a ouvert ne le tranche pas (quatre yeux), et seul son auteur retire un brouillon |

Index **(en cours)** : `(country, status)`, `(date)`.

Le contexte (pays, équipe, propriétaire, date) est porté par le dossier, mais
chaque ligne le **duplique** pour une traçabilité ligne par ligne.

### 5.3 `Expense` — ligne de dépense

| Champ | Type | Notes |
|---|---|---|
| `dossier` | FK → Dossier | |
| `country` | FK → Country (PROTECT) | dupliqué |
| `team` / `owner` | FK (null) | dupliqués |
| `date` | DateTime | stockée en UTC, lue dans le fuseau du pays |
| `place` | Char(180) | lieu |
| `title` | Char(250) | libellé de la transaction |
| `description` | Text | |
| `project`, `expense_title`, `marketing_category`, `beneficiary` | FK (null) | |
| `budget` | FK → Budget (PROTECT, null) | enveloppe imputée, résolue automatiquement ; **obligatoire dès que la ligne n'est plus un brouillon** |
| `amount` | Decimal(16,2) ≥ 0 | dans la devise du pays ; c'est ce montant qui pèse sur l'enveloppe |
| `justified_amount` | Decimal(16,2) | défaut 0, ≤ `amount` |
| `original_currency` | Char(3) | devise du décaissement, vide si devise du pays |
| `original_amount` | Decimal(16,2) (null) | tel qu'il figure sur la pièce |
| `original_rate` | Decimal(18,6) (null) | taux figé à la saisie |
| `payment_method` | Char(20) | `cash`, `transfer`, `mobile`, `card`, `check`, `other` |
| `status` | Char(20) | circuit (5.5) |
| `note` | Text | |
| `control_note` | Text | **(en cours)** motif du contrôle (mise en contrôle, rejet) |
| `created_by` | Char(180) | identité en texte de qui a saisi la ligne ; ne peut pas la justifier |

Champ **calculé** : `gap = amount − justified_amount`, jamais saisi.

Contraintes en base **(en cours)** — les invariants sont posés en base
parce que l'admin et les scripts ne passent pas par les sérialiseurs :

- `depense_montant_positif` — `amount ≥ 0` ;
- `depense_justifie_borne` — `0 ≤ justified_amount ≤ amount` ;
- `depense_devise_origine_coherente` — devise, montant et taux d'origine
  tous vides ou tous renseignés ;
- `depense_declaree_imputee` — hors brouillon, `budget` est renseigné.

Index **(en cours)** : `(budget, status)`, `(country, status, date)`, `(date)`.

### 5.4 `Proof` — pièce justificative

Rattachée au **dossier** : l'ensemble documentaire du N°ORDRE.

| Champ | Type | Notes |
|---|---|---|
| `dossier` | FK → Dossier | |
| `file` | FileField | stockage objet S3/MinIO (`AWS_S3_ENDPOINT_URL`), disque local à défaut ; liste blanche de formats, taille ≤ `MAX_PROOF_SIZE` |
| `original_name` | Char(255) | nom du fichier déposé |
| `kind` | Char(32) | `receipt`, `invoice`, `discharge`, `deliverable`, `other` |
| `status` | Char(20) | `received`, `incomplete`, `to_review`, `validated`, `rejected`, `archived` |
| `is_complete` | Bool | reprend la nuance « reçu (justif incomplet) » du fichier source |
| `sha256` | Char(64), indexé | empreinte : détecte les doublons et toute altération |
| `size` | BigInteger | octets |
| `content_type` | Char(120) | type MIME |
| `version` | Integer | défaut 1 |
| `replaces` | OneToOne → Proof (null) | la version remplacée, archivée |
| `uploaded_by` | Char(180) | identité en texte |
| `rejection_reason` | Text | obligatoire au rejet |

Redéposer un fichier déjà présent sur le même dossier (même `sha256`) est
refusé, sauf remplacement explicite. Le téléchargement passe par une vue
authentifiée, jamais par une URL signée : le périmètre est vérifié à chaque
accès et chaque téléchargement laisse une trace dans le journal d'audit.
Index **(en cours)** : `(dossier, status)`.

### 5.5 Circuit de justification

Le même circuit s'applique au dossier **et** à chaque ligne
(`expenses/workflow.py`, `Status`) :

```
draft ─▶ submitted ─▶ in_review ─▶ justified ──▶ closed
brouillon   soumis     en contrôle └▶ unjustified ┘
                                      non justifié
```

- `submit` : le pays soumet le dossier, ses lignes partent avec lui. Un
  dossier vide ne se soumet pas ; un dossier sans pièce se soumet avec un
  avertissement (`warn_without_proof_submission`).
- `review` : mise en contrôle, facultative sauf si `require_review_step`.
- `justify` / `reject` : le siège constate ; `reject` exige un motif et
  laisse la ligne **non justifiée** — elle pèse toujours sur l'enveloppe.
  Une pièce déposée après coup permet de la justifier ensuite.
- `close` : clôture.

**Une dépense soumise est irréversible** : elle ne revient pas au brouillon,
ne se modifie plus, ne se supprime pas. Seul un brouillon peut être retiré,
par son auteur, et ce retrait est journalisé. Le statut n'est jamais
modifiable par écriture de champ ; seules ces transitions le font évoluer,
et chacune écrit une entrée `AuditLog`.

### 5.6 `AuditLog` — journal des actions sensibles

| Champ | Type | Notes |
|---|---|---|
| `user` | Char(180) | identité en texte |
| `action` | Char(32) | `created`, `updated`, `submitted`, `reviewed`, `justified`, `unjustified`, `approved` / `rejected` (contrôle d'une pièce), `deleted` (brouillon), `closed`, `proof_uploaded`, `proof_replaced`, `proof_to_review`, `downloaded` (pièce ou export), `imported` (Excel) |
| `object_type` / `object_id` | Char(64) / Integer | cible |
| `label` | Char(250) | |
| `country` | FK → Country (null) | pour le cloisonnement du journal |
| `detail` | JSON | ancienne et nouvelle valeur, motif… |
| `ip_address` | IP (null) | adresse réelle du client, derrière `DJANGO_NUM_PROXIES` proxys |
| `user_agent` | Char(250) | |
| `created_at` | DateTime | |

Index : `(object_type, object_id)` ; **(en cours)** `(created_at)`,
`(country, created_at)`, `(user)`.

## 6. Notifications (`notifications`)

### `Notification`

| Champ | Type | Notes |
|---|---|---|
| `recipient` | FK → User | |
| `kind` | Char(32) | `budget_threshold`, `budget_overrun`, `expense_submitted`, `expense_rejected`, `proof_missing`, `proof_incomplete`, `reallocation_requested`, `storage_error` |
| `level` | Char | `info`, `warning`, `critical` |
| `title`, `body`, `link` | | |
| `country` | FK → Country (null) | |
| `dedup_key` | Char | évite de signaler deux fois le même franchissement |
| `read_at`, `emailed_at`, `created_at` | DateTime | |

Les alertes sont **calculées** à chaque lecture du tableau de bord ; seule
leur notification (`manage.py notify_alerts`, lancé par l'ordonnanceur)
écrit ces lignes et envoie les e-mails.

## 7. Relations (synthèse)

```
Country 1─* Budget ─* BudgetReallocation (source / target)
Country 1─* Dossier 1─* Expense *─1 Budget
Country 1─* Expense              Dossier 1─* Proof ─1 Proof (replaces)
Country 1─* Beneficiary          Expense *─1 Beneficiary
Country *─* UserProfile          UserProfile 1─1 User
ExchangeRate (currency, valid_from)
AuditLog, ChangeLog, Notification ─▶ Country (null)
```

## 8. Décisions de modélisation validées

| # | Décision | Choix |
|---|---|---|
| 1 | Contexte (pays, équipe, propriétaire, date) | **dupliqué sur chaque ligne** |
| 2 | ÉCART | **calculé** = `amount − justified_amount` |
| 3 | Pièces justificatives | **au niveau du dossier** |
| 4 | Circuit | **complet**, sur le dossier et sur chaque ligne |
| 5 | Prospect / bénéficiaire | entité `Beneficiary` dédiée, typée, **par pays** |
| 6 | Enveloppe | par pays et année, sous-enveloppes selon **une** dimension (projet, équipe ou manager) |
| 7 | Dépense non justifiée | **pèse sur l'enveloppe** ; l'écart se lit, ne se corrige pas |
| 8 | Dépense soumise | **irréversible** ; seul un brouillon se retire |
| 9 | Suppression | **aucune**, hors brouillon ; désactivation (`is_active`) |
| 10 | Identités dans les journaux | **en texte**, pas en clé étrangère |
| 11 | Décaissement en devise étrangère | montant et taux d'origine **figés** sur la ligne, enveloppe monodevise |
| 12 | Politique du circuit | `WorkflowConfiguration`, singleton modifiable par le siège |

## 9. Stockage des fichiers

Les pièces vont dans un stockage objet compatible S3 — MinIO dans les piles
Docker (`AWS_S3_ENDPOINT_URL`, `AWS_STORAGE_BUCKET_NAME`, seau créé au
démarrage par `manage.py ensure_bucket`) — ou sur disque local
(`MEDIA_ROOT`) quand l'URL est vide, ce que font les tests. Les fichiers ne
sont jamais servis directement : voir 5.4.
