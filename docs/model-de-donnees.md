# Modèle de données — JUSTI INNOV

> Document de référence du modèle de données, **tenu à jour avec le code** :
> ce qui est écrit ici correspond aux modèles Django (`backend/*/models.py`)
> et à leurs migrations. Il fige les décisions de modélisation (section 5) et
> sert de socle à l'API REST et au frontend. Une entité qui change se met à
> jour ici dans le même commit.

## 1. Rappel des objectifs

- Attribuer une **enveloppe annuelle par pays** (super administrateurs :
  DG, DO, CEO).
- Suivre en temps réel et de façon **traçable** l'utilisation de l'enveloppe
  par les managers et équipes.
- Relier chaque dépense à son contexte : **date/heure, pays, utilisateur, lieu,
  montant, intitulé/projet, prospect ou bénéficiaire, statut de justification
  et preuve documentaire** (PDF, reçu, décharge, facture ou autre livrable).
- Conserver l'historique des changements (audit), **sans limite de durée** :
  rien n'est jamais purgé.

Le but n'est pas d'autoriser des dépenses : c'est de savoir **ce qui a été
dépensé, quand, où, au profit de qui — et où est la preuve**. D'où
« justifié » plutôt que « validé ».

### Correspondance avec le fichier Excel « BASE DE DONNEES ACTIONS »

Le classeur réel du client (un par pays et par période) se présente ainsi :
une feuille « BASE DE DONNEES ACTIONS », un titre fusionné en ligne 2, une
note en ligne 4, **l'en-tête en ligne 7** et neuf colonnes exactement —
N°ORDRE · DATE · TEAM · OWNER · LIBELLE DES TRANSACTIONS · DEPENSES ·
MONTANT JUSTIFIER · ECART · PIECES JUSTIFICATIVES. Les N°ORDRE y sont des
entiers **numérotés par pays** (1 → n, un numéro regroupant jusqu'à
quelques dizaines de lignes), les dates n'ont pas d'heure, les montants sont
entiers, MONTANT JUSTIFIER est parfois vide, et la colonne des pièces porte
des mentions comme « Reçu » ou « Reçu(justif incomplet) ».

L'export `/api/exports/expenses.xlsx` reprend ces colonnes en y ajoutant
PAYS, DEVISE D'ORIGINE, MONTANT D'ORIGINE et STATUT (13 colonnes, en-tête en
première ligne). L'import `/api/imports/expenses.xlsx` lit **les deux
formats** : il cherche la ligne d'en-tête dans les quinze premières lignes
(celle qui porte N°ORDRE et DEPENSES) et ne rend obligatoires que les six
colonnes du classeur historique.

| Colonne Excel | Modèle | Notes |
|---|---|---|
| N°ORDRE | `Dossier.number` | entité regroupant lignes et preuves ; **unique par pays** ; un entier est lu en texte (« 12 », jamais « 12.0 ») |
| DATE | `Expense.date` | date, avec ou sans heure, lue dans le fuseau du pays |
| PAYS | `Expense.country` | *facultative* : absente du classeur historique (mono-pays), le pays vient alors du paramètre `country` de la requête, obligatoire et vérifié contre le périmètre ; il sert aussi de repli si la cellule est vide |
| TEAM | `Expense.team` | dupliqué sur chaque ligne ; **une équipe inconnue est créée dans le pays** |
| OWNER | `Expense.owner` | manager propriétaire ; **un manager inconnu est créé et rattaché au pays** (un homonyme d'un autre pays n'est pas réutilisé) |
| LIBELLE DES TRANSACTIONS | `Expense.title` | |
| DEPENSES | `Expense.amount` | dans la devise du pays |
| DEVISE D'ORIGINE | `Expense.original_currency` | *facultative* ; vide si décaissée dans la devise du pays |
| MONTANT D'ORIGINE | `Expense.original_amount` | *facultative* ; tel qu'il figure sur la pièce |
| MONTANT JUSTIFIER | — | **ignorée à l'import** : le siège constate, un montant justifié ne s'importe pas ; l'export l'écrit depuis `Expense.justified_amount` |
| ECART | — | **ignorée à l'import** ; l'export l'écrit, *calculé* = `amount − justified_amount`, jamais stocké |
| STATUT | — | **ignorée à l'import** : tout arrive en brouillon ; l'export l'écrit depuis `Expense.status` |
| PIECES JUSTIFICATIVES | `Expense.note` à l'import (« Pièce : Reçu(justif incomplet) ») ; `Proof` à l'export | la mention du classeur est une information, pas une preuve : la pièce elle-même se dépose ensuite sur le dossier |

Les entités de référentiel créées par l'import passent par le modèle, donc
par l'historique (`ChangeLog`), au nom de celui qui importe ; la
prévisualisation (`dry_run`) les compte sans les créer.

> **Interprétation `N°ORDRE`** : le numéro d'ordre devient une entité
> « dossier de justification » regroupant les preuves associées à une même
> opération. Les lignes Excel deviennent des lignes de dépenses rattachées à
> ce dossier. Comme dans le classeur, le numéro est **propre à chaque pays**.

## 2. Référentiel (`core`)

Toutes ces entités héritent de `TimeStampedModel` (`created_at`,
`updated_at`) et se retirent par **désactivation** (`is_active`), jamais par
suppression : l'API répond 405 sur `DELETE`.

- `Country` — pays : `country_ref` (identifiant fonctionnel, ex. `TG-01`),
  `name`, `code` ISO validé contre la liste des **dix-sept filiales**
  (`core/africa.py` : Sénégal, Mali, Côte d'Ivoire, Madagascar, Cameroun,
  Gabon, Mauritanie, Burkina Faso, Niger, Bénin, Guinée, Togo, Gambie,
  Djibouti, Tchad, Congo, RDC), `currency`, `currency_symbol`, `timezone`,
  `managers` (M2M), `is_active`. Seules la Côte d'Ivoire et le Togo sont
  créées au démarrage.
- `Manager` — responsable ; peut exister sans compte utilisateur.
- `Team` (`name` unique par pays, `unique_equipe_par_pays`), `CostCenter`
  (`code` unique par pays), `Project` (`status`, `budget` ; `name` unique
  par pays, `unique_projet_par_pays`), `ExpenseTitle` (`label` unique par
  pays), `MarketingCategory` (`name` unique par pays) — tous rattachés à un
  pays. Le même nom reste possible dans deux pays : le référentiel est
  cloisonné. La migration `core.0010` a renommé les homonymes préexistants
  avec un suffixe « (2) », « (3) »… plutôt que de les fusionner.
- `ChangeLog` — journal des changements du référentiel et des budgets :
  `model_name`, `object_id`, `label`, `action` (création, mise à jour,
  changement de rattachement, désactivation, réactivation, suppression,
  réinitialisation et changement de mot de passe, activation
  (`totp_confirmed`) et réinitialisation (`totp_reset`) de la double
  authentification, connexion, échec de connexion — `login_failed`, avec
  `changed_fields = ["totp"]` quand c'est le code qui manque ou est faux —,
  déconnexion), `from_value` / `to_value`, `changed_fields`,
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
| `role` | Char(32) | `manager`, `dm`, `df`, `admin`, `super_admin` (migration `accounts.0002` : `owner` → `manager`, `country_manager` → `dm`, `controller` → `df`, `doo` → `super_admin`, `auditor` → `admin`) |
| `countries` | M2M → Country | périmètre ; vide pour `dm` et `df` = tous les pays — ce sont les deux rôles du siège restrictibles à des pays. `admin` et `super_admin` sont toujours globaux. Un `manager` sans périmètre ne voit **rien** |
| `teams` | M2M → Team | pour un `manager` : restreint sa vue à ces équipes, sur le queryset (`CountryScopedMixin.team_lookup` : `team__in` pour les dossiers, les dépenses et les équipes, `dossier__team__in` pour les pièces) ; vide, il voit tout son pays. Sans effet sur les autres rôles |
| `manager` | FK → Manager (null) | le manager du référentiel que ce compte incarne |
| `must_change_password` | Bool | mot de passe provisoire : la plateforme reste fermée tant qu'il n'est pas remplacé |
| `totp_secret` | Char(64) | secret TOTP (RFC 6238), vide tant que le compte n'est pas enrôlé ; remis une seule fois (`POST /api/me/2fa/enrol/` : `otpauth_uri`, `qr_png_base64`, `secret`), jamais exposé ensuite par l'API |
| `totp_confirmed_at` | DateTime (null) | date du premier code valide (`POST /api/me/2fa/confirm/ {code}`). Vide, l'enrôlement est proposé depuis le menu du compte ; si `DJANGO_TOTP_REQUIRED` est actif, la plateforme reste fermée au compte (`403 {"totp_setup_required": true}`), comme pour un mot de passe provisoire. `GET /api/me/` expose la politique (`totp_required`) et l'état (`totp_confirmed`). Pour un compte enrôlé, l'obtention du jeton exige le `code` (`400 totp_required`). `POST /api/users/{id}/reset-2fa/` (administrateurs, hiérarchie respectée) efface les deux champs. `seed_users` accepte `totp_secret` pour les environnements jetables |
| `language` | Char(8) | `fr` (défaut) ou `en` : préférence d'affichage de l'interface. La langue d'une réponse de l'API suit l'en-tête `Accept-Language` |

Les cinq rôles suivent l'organisation du groupe. Côté pays, un seul
compte : le `manager` (Manager — pays) engage la dépense, la saisit,
dépose la pièce et soumet le dossier ; le référentiel de son pays (équipes,
projets, intitulés, catégories, bénéficiaires) est tenu par la RH. Côté siège : le `dm` (DM — directeur manager) met en contrôle une
dépense soumise ; le `df` (DF — directeur financier) constate — justifie,
refuse, clôture ; l'`admin` (Administrateur — RH) tient les comptes,
l'audit, le référentiel de tous les pays, les imports et exports et rouvre
un dossier ; le `super_admin` (DG, DO, CEO, DEV) peut tout, et seul il
attribue les enveloppes, arbitre les réallocations et tient les taux de
change. **Le `dm` et le `df` n'ont aucun droit d'administration** : ils ne
sont ni administrateurs ni super administrateurs, et n'apparaissent que
dans `REVIEW_ROLES` (`dm`, `df`), `VALIDATION_ROLES` (`df`) et
`HISTORY_READ_ROLES` (historique du référentiel, sur leur périmètre).
`dm` et `df` sont restrictibles à des pays, `admin` et `super_admin`
jamais. Il n'y a ni « direction des opérations » ni « auditeur »
distincts. Les ensembles de rôles sont dans `accounts/permissions.py` :
`BUDGET_WRITE_ROLES` = `OVERRUN_APPROVERS` = `super_admin` ;
`AUDIT_READ_ROLES` = `EXPORT_ROLES` = `REOPEN_ROLES` = `super_admin`,
`admin`. `/api/me/` les traduit en capacités, dont `review_expenses` (mise
en contrôle) distincte de `validate_expenses` (constat).

Un manager ne justifie jamais une dépense, et celui qui a saisi une
dépense ne la justifie pas lui-même, fût-il au siège. L'adresse e-mail
d'un compte doit appartenir à un domaine de `ALLOWED_EMAIL_DOMAINS`
(`innovpharma.net` par défaut ; `accounts/validators.py`). Les identités
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
| `overrun_policy` | Char(20) | `block` (refuser la justification au-delà), `warn` (alerter), `approval` (réserver la justification aux super administrateurs) ; défaut lu dans `WorkflowConfiguration` |
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
`reject` exige un motif. Demander comme décider relève de
`BUDGET_WRITE_ROLES` (`super_admin`), et celui qui demande ne décide pas.

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
| `number` | Char(50) | **N°ORDRE**, **unique par pays** (`unique_dossier_par_pays`), saisi ou importé : le classeur du client numérote de 1 à n dans chaque pays |
| `label` | Char(250) | |
| `country` | FK → Country (PROTECT) | |
| `team` | FK → Team (null) | contexte |
| `owner` | FK → Manager (null) | responsable |
| `date` | Date | |
| `status` | Char(20) | circuit (5.5) |
| `note` | Text | remarque de contrôle |
| `created_by` | Char(180) | identité en texte de qui a ouvert le dossier : celui qui l'a ouvert ne le tranche pas (quatre yeux), et seul son auteur retire un brouillon |
| `reopen_note` | Text | motif de la dernière réouverture (`note` de `reopen`, obligatoire) ; vide si le dossier n'a jamais été rouvert. Qui et quand sont dans `AuditLog` (`reopened`) |

Index : `(country, status)`, `(date)`.

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
| `control_note` | Text | motif du contrôle (mise en contrôle, rejet) |
| `created_by` | Char(180) | identité en texte de qui a saisi la ligne ; ne peut pas la justifier |

Champ **calculé** : `gap = amount − justified_amount`, jamais saisi.

Contraintes en base — les invariants sont posés en base
parce que l'admin et les scripts ne passent pas par les sérialiseurs :

- `depense_montant_positif` — `amount ≥ 0` ;
- `depense_justifie_borne` — `0 ≤ justified_amount ≤ amount` ;
- `depense_devise_origine_coherente` — devise, montant et taux d'origine
  tous vides ou tous renseignés ;
- `depense_declaree_imputee` — hors brouillon, `budget` est renseigné.

Index : `(budget, status)`, `(country, status, date)`, `(date)`.

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
Index : `(dossier, status)`.

### 5.5 Circuit de justification

Le même circuit s'applique au dossier **et** à chaque ligne
(`expenses/workflow.py`, `Status`) :

```
draft ─▶ submitted ─▶ in_review ─▶ justified ──▶ closed
brouillon   soumis     en contrôle └▶ unjustified ┘
   ▲           │           │          non justifié │
   └───────────┴───────────┴───────────────────────┘  reopen (administrateur, motif)
```

- `submit` : le manager soumet le dossier, ses lignes partent avec lui. Un
  dossier vide ne se soumet pas ; **chaque ligne doit porter une équipe et
  un manager** (cahier des charges §7), sinon la soumission est refusée en
  nommant les lignes incomplètes ; un dossier sans pièce se soumet avec un
  avertissement (`warn_without_proof_submission`).
- `review` : mise en contrôle par le DM (`review_expenses`), facultative
  sauf si `require_review_step`.
- `justify` / `reject` : le DF constate (`validate_expenses`) ; `reject`
  exige un motif et
  laisse la ligne **non justifiée** — elle pèse toujours sur l'enveloppe.
  Une pièce déposée après coup permet de la justifier ensuite.
- `close` : clôture.
- `reopen` : **réouverture** (`POST /api/dossiers/{id}/reopen/ {note}`),
  par `REOPEN_ROLES` (`admin`, `super_admin`) seulement, avec un motif
  obligatoire (`MOTIVATED_ACTIONS = {reject, reopen}`). Ramène au brouillon
  un dossier soumis, en contrôle ou non justifié, et ses lignes avec lui —
  elles perdent leur imputation (`budget = null`), recalculée à la prochaine
  soumission ; refusée dès qu'une ligne est justifiée ou clôturée
  (`REOPEN_BLOCKING_STATUSES`, réponse `400` sur `expenses`). Les comptes
  qui suivent le pays sont notifiés (`dossier_reopened`) et le dossier devra
  être soumis à nouveau. Elle sert à demander des
  comptes — une ligne mal imputée, une pièce qui ne correspond pas —, jamais
  à corriger en silence : le motif est conservé sur le dossier et dans
  `AuditLog`, sur le dossier et sur chaque ligne.

**Une dépense soumise est irréversible** : elle ne revient pas au brouillon,
ne se modifie plus, ne se supprime pas. Seul un brouillon peut être retiré,
par son auteur, et ce retrait est journalisé. La réouverture est l'unique
exception, et elle est tracée, motivée et bornée comme ci-dessus. Le statut
n'est jamais modifiable par écriture de champ ; seules ces transitions le
font évoluer, et chacune écrit une entrée `AuditLog`.

### 5.6 `AuditLog` — journal des actions sensibles

Consultable par `AUDIT_READ_ROLES` (`admin`, `super_admin`) : la RH, qui
audite, et la direction. Le DM et le DF n'y accèdent pas — le journal relit
leurs décisions.

| Champ | Type | Notes |
|---|---|---|
| `user` | Char(180) | identité en texte |
| `action` | Char(32) | `created`, `updated`, `submitted`, `reviewed`, `justified`, `unjustified`, `approved` / `rejected` (contrôle d'une pièce), `deleted` (brouillon), `closed`, `reopened` (réouverture, avec le motif ; sur le dossier et sur chaque ligne), `proof_uploaded`, `proof_replaced`, `proof_to_review`, `downloaded` (pièce, ou export avec `detail = {year, month, country, format}`), `imported` (Excel) |
| `object_type` / `object_id` | Char(64) / Integer | cible |
| `label` | Char(250) | |
| `country` | FK → Country (null) | pour le cloisonnement du journal |
| `detail` | JSON | ancienne et nouvelle valeur, motif… |
| `ip_address` | IP (null) | adresse réelle du client, derrière `DJANGO_NUM_PROXIES` proxys |
| `user_agent` | Char(250) | |
| `created_at` | DateTime | |

Index : `(object_type, object_id)`, `(created_at)`, `(country, created_at)`,
`(user)`.

## 6. Notifications (`notifications`)

### `Notification`

| Champ | Type | Notes |
|---|---|---|
| `recipient` | FK → User | |
| `kind` | Char(32) | `budget_threshold`, `budget_overrun`, `expense_submitted`, `expense_rejected`, `dossier_reopened` (aux comptes qui suivent le pays), `proof_missing`, `proof_incomplete`, `reallocation_requested`, `storage_error` |
| `level` | Char | `info`, `warning`, `critical` |
| `title`, `body`, `link` | | |
| `country` | FK → Country (null) | |
| `dedup_key` | Char | évite de signaler deux fois le même franchissement |
| `read_at`, `emailed_at`, `created_at` | DateTime | |

Les alertes sont **calculées** à chaque lecture du tableau de bord ; seule
leur notification (`manage.py notify_alerts`, lancé par l'ordonnanceur)
écrit ces lignes et envoie les e-mails. Titre, corps et e-mail sont rendus
dans la langue du destinataire (`UserProfile.language`). Le rapport
périodique n'attache le classeur qu'aux administrateurs (`EXPORT_ROLES`).

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
| 13 | N°ORDRE | **unique par pays**, comme dans le classeur du client ; deux pays peuvent porter le même numéro |
| 14 | Nom d'équipe, nom de projet | **uniques par pays** ; le même nom reste possible dans deux pays |
| 15 | Champs obligatoires à la soumission (CdC §7) | **équipe et manager** sur chaque ligne, vérifiés à la soumission seulement — pas de contrainte en base, l'import crée des brouillons incomplets. **Lieu, projet et intitulé restent facultatifs** : le classeur historique ne les porte pas, les exiger rendrait l'historique impossible à déclarer |
| 16 | Import Excel | lit le classeur historique (en-tête cherché dans les 15 premières lignes, colonnes PAYS / devise / statut facultatives) ; équipes et managers inconnus **créés dans le pays** ; MONTANT JUSTIFIER, ECART et STATUT ignorés |
| 17 | Périmètre géographique | **dix-sept filiales**, listées dans `core/africa.py` ; Côte d'Ivoire et Togo créées au démarrage, les autres à leur entrée dans le dispositif |
| 18 | Rôles | **cinq** : `manager`, `dm`, `df`, `admin`, `super_admin`. Ni direction des opérations ni auditeur distincts. **Le DM et le DF n'ont aucun droit d'administration** (décision du produit) : ils ne sont ni administrateurs ni super administrateurs et gardent leurs seules fonctions de contrôle. Enveloppes, réallocations, taux de change et dépassements : `BUDGET_WRITE_ROLES` = `OVERRUN_APPROVERS` = `super_admin` seul — le DF constate, il n'attribue pas. Journal d'audit : `AUDIT_READ_ROLES` = `admin`, `super_admin` (RH et direction) ; l'historique du référentiel reste ouvert au siège entier. `dm` et `df` restrictibles à des pays |
| 19 | Périmètre d'un manager | **ses équipes** (`UserProfile.teams`), vérifié sur le queryset (`CountryScopedMixin.team_lookup`) ; sans équipe rattachée, tout son pays. Les autres rôles ne sont pas restreints par équipe |
| 20 | Réouverture | **seule exception à l'irréversibilité** : `REOPEN_ROLES` (`admin`, `super_admin`), motif obligatoire (`Dossier.reopen_note`), `AuditLog` `reopened` sur le dossier et ses lignes, lignes en brouillon sans imputation, notification aux `dm` et `manager` du pays ; refusée dès qu'une ligne est justifiée ou clôturée. Pour demander des comptes, jamais pour corriger en silence |
| 21 | Fichiers | import Excel et exports (`xlsx`, `csv`, `docx`, `pdf` ; `year`, `month` facultatif, `country`) **réservés à `EXPORT_ROLES`**, lecture comprise ; tous les autres travaillent dans l'application. CSV UTF-8 avec BOM, séparateur `;` ; totaux à devise unique seulement. Chaque export est journalisé avec ses paramètres |
| 22 | Rétention | **illimitée** : aucune purge de dossier, pièce, journal ou notification ; les sauvegardes gardent une copie mensuelle pour toujours (`deploy/sauvegarder.sh`) |
| 23 | Authentification | **TOTP proposé, obligatoire seulement si `DJANGO_TOTP_REQUIRED`** (`totp_secret`, `totp_confirmed_at` ; politique exposée par `/api/me/` `totp_required`) — l'obligation est reportée par la direction, le code reste prêt ; réinitialisation par un administrateur seulement, tracée ; adresse e-mail dans `ALLOWED_EMAIL_DOMAINS` |
| 24 | Langue | **bilingue français / anglais** : `Accept-Language` côté API, préférence `language` sur le profil ; le français est la référence des messages, l'anglais vient des catalogues `locale/en` des six applications ; notifications et e-mails dans la langue du destinataire |
| 25 | Supports | web et **application de bureau installable (PWA)** ; pas d'usage mobile prévu |
| 26 | Siège et pays | **le manager déclare, le DM contrôle, le DF constate.** Le `manager` est le seul compte de pays ; `dm` et `df` sont au siège. La mise en contrôle (`review_expenses`) et le constat (`validate_expenses`) sont deux capacités distinctes ; `admin` et `super_admin` ont les deux. La RH tient le référentiel de tous les pays, le manager celui du sien |

### Décisions contraires au cadrage initial, assumées

Le cadrage d'origine n'est plus dans le dépôt : il portait le nom d'un autre
projet et ne décrivait pas l'application telle qu'elle est. Ce qu'il
demandait et que l'on a choisi de ne pas faire reste consigné ici, pour que
la question ne soit pas rouverte par oubli.

| # | Ce que demandait le cadrage | Choix retenu et raison |
|---|---|---|
| C1 | Validation par délégation au responsable pays | **Pas de délégation.** Le manager déclare, le DM contrôle, le DF constate : un manager qui justifierait les dépenses de son pays viderait l'application de son objet. Les rôles de validation (`VALIDATION_ROLES`) excluent le rôle pays. |
| C2 | Opération de correction après soumission | **Aucune correction après soumission.** Une dépense soumise est irréversible ; la seule voie est `justify` / `reject` (motif obligatoire) puis clôture. Une erreur se traite par une nouvelle ligne ou un nouveau dossier, jamais en réécrivant la déclaration. La réouverture (décision 20) n'est pas une correction : elle renvoie tout le dossier au pays, motif à l'appui, sous les yeux de l'audit. |
| C3 | Rapports par équipe, manager ou période libre | **Rapport PDF par pays et exercice, exports par exercice ou par mois** (`/api/exports/`), réservés aux administrateurs. Les autres découpages se lisent dans le tableau de bord (`/api/dashboard/breakdown/`). |
| C4 | Sous-enveloppes par catégorie | **Par projet, équipe ou manager — pas par catégorie.** Une sous-enveloppe suit une dimension d'imputation d'une ligne ; la catégorie marketing est une étiquette d'analyse, pas une responsabilité budgétaire. |
| C5 | Six acteurs, dont une direction des opérations et un auditeur | **Cinq rôles** (décision 18) : la DO est super administratrice, l'audit revient à la RH. Deux rôles de plus, c'est deux listes de droits de plus à maintenir pour des personnes qui, dans le groupe, sont les mêmes. |
| C6 | Périmètre par équipe : question laissée ouverte | **Tranchée** (décision 19) : un manager ne voit que ses équipes. |

## 9. Stockage des fichiers

Les pièces vont dans un stockage objet compatible S3 — MinIO dans les piles
Docker (`AWS_S3_ENDPOINT_URL`, `AWS_STORAGE_BUCKET_NAME`, seau créé au
démarrage par `manage.py ensure_bucket`) — ou sur disque local
(`MEDIA_ROOT`) quand l'URL est vide, ce que font les tests. Les fichiers ne
sont jamais servis directement : voir 5.4.
