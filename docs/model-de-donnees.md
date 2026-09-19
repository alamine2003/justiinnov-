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
| `teams` | M2M → Team | pour un `manager` : restreint sa vue à ces équipes, sur le queryset (`CountryScopedMixin.team_lookup` : `team__in` pour les dossiers, les dépenses et les équipes, `dossier__team__in` pour les pièces) ; vide, il voit tout son pays. Sans effet sur les autres rôles. Administrable par l'API (`teams` en écriture, `teams_detail` en lecture sur `/api/users/`), **borné aux pays du compte** — une équipe d'un autre pays est refusée —, chaque changement journalisé (`ChangeLog`, avant/après) |
| `manager` | FK → Manager (null) | le manager du référentiel que ce compte incarne |
| `must_change_password` | Bool | mot de passe provisoire : la plateforme reste fermée tant qu'il n'est pas remplacé |
| `totp_secret` | Char(64) | secret TOTP (RFC 6238), vide tant que le compte n'est pas enrôlé ; remis une seule fois (`POST /api/me/2fa/enrol/` : `otpauth_uri`, `qr_png_base64`, `secret`), jamais exposé ensuite par l'API |
| `totp_last_counter` | BigInteger (null) | dernier compteur TOTP accepté : **un code ne sert qu'une fois**, même encore valide dans sa fenêtre ; remis à zéro à chaque nouveau secret et à la réinitialisation |
| `totp_confirmed_at` | DateTime (null) | date du premier code valide (`POST /api/me/2fa/confirm/ {code}`). Vide, l'enrôlement est proposé depuis le menu du compte ; si `DJANGO_TOTP_REQUIRED` est actif, la plateforme reste fermée au compte (`403 {"totp_setup_required": true}`), comme pour un mot de passe provisoire. `GET /api/me/` expose la politique (`totp_required`) et l'état (`totp_confirmed`). Pour un compte enrôlé, l'obtention du jeton exige le `code` (`400 totp_required`). `POST /api/users/{id}/reset-2fa/` (administrateurs, hiérarchie respectée) efface les deux champs. `seed_users` accepte `totp_secret` pour les environnements jetables |
| `language` | Char(8) | `fr` (défaut) ou `en` : préférence d'affichage de l'interface. La langue d'une réponse de l'API suit l'en-tête `Accept-Language`. Comme `role`, tout changement est journalisé par `accounts.signals` au moment où le profil s'enregistre, quel que soit le chemin — API, `seed_users` ou admin Django |

Le **nom de compte (`username`) est immuable** après création : les
contrôles à quatre yeux (celui qui a saisi une dépense ne la justifie pas)
comparent sur lui, et il nomme chaque entrée d'historique. `GET /api/me/`
renvoie, pour chaque pays du périmètre (`countries[]`), son `timezone` et
sa `currency`, que l'interface se contente d'afficher. Le back-office
Django (`/admin/`) applique les mêmes verrous que l'API — mot de passe
provisoire, double authentification si elle est exigée — et n'est pas
routé depuis l'extérieur en production.

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
sont ni administrateurs ni super administrateurs, et n'apparaissent par
défaut que dans `expenses.review` (`dm`, `df`), `expenses.validate`,
`expenses.close`, `proofs.review` (`df`) et `history.read` (historique du
référentiel, sur leur périmètre).
`dm` et `df` sont restrictibles à des pays, `admin` et `super_admin`
jamais. Il n'y a ni « direction des opérations » ni « auditeur »
distincts. Les droits sont des capacités nommées (`accounts/permissions.py`,
`CAPACITES`, décision 43), avec leurs rôles par défaut : `budgets.*`,
`reallocations.*`, `rates.manage` à `super_admin` ; `audit.read`,
`data.export`, `data.import`, `dossiers.reopen`, `users.*`,
`configuration.manage` à `super_admin` et `admin` ; `expenses.review` (mise
en contrôle) distincte de `expenses.validate` (constat). Les administrateurs
règlent la matrice dans la configuration ; `/api/me/` la traduit en
capacités.

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
`reject` exige un motif. Demander (`reallocations.request`) comme décider
(`reallocations.decide`) relève de `super_admin` par défaut, et celui qui
demande ne décide pas.

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
- `review` : mise en contrôle par le DM (`expenses.review`), facultative
  sauf si `require_review_step`.
- `justify` / `reject` : le DF constate (`expenses.validate`) ; `reject`
  exige un motif et
  laisse la ligne **non justifiée** — elle pèse toujours sur l'enveloppe.
  Une pièce déposée après coup permet de la justifier ensuite.
- `close` : clôture.
- `reopen` : **réouverture** (`POST /api/dossiers/{id}/reopen/ {note}`),
  par `dossiers.reopen` (`admin`, `super_admin` par défaut, jamais le pays)
  seulement, avec un motif
  obligatoire (`MOTIVATED_ACTIONS = {reject, reopen}`). Ramène au brouillon
  un dossier soumis, en contrôle ou non justifié, et ses lignes avec lui —
  elles perdent leur imputation (`budget = null`), recalculée à la prochaine
  soumission ; refusée dès qu'une ligne est justifiée ou clôturée
  (`REOPEN_BLOCKING_STATUSES`, réponse `400` sur `expenses`). Les
  **managers du pays** — ceux qui déclarent, donc qui ont à corriger —
  sont notifiés (`dossier_reopened`, `notifications/triggers.py`) ; pas le
  DM, qui n'a rien à refaire tant que le dossier n'est pas resoumis. Le
  dossier devra être soumis à nouveau. Elle sert à demander des
  comptes — une ligne mal imputée, une pièce qui ne correspond pas —, jamais
  à corriger en silence : le motif est conservé sur le dossier et dans
  `AuditLog`, sur le dossier et sur chaque ligne.
- `rectify` : **rectification d'un constat**, la seconde exception, là où
  la réouverture s'arrête. Une ligne **justifiée ou clôturée** l'a été à
  tort (montant justifié faux, pièce prise pour une autre) : n'importe qui
  le **demande** (`POST /api/rectifications/ {expense, motif}`,
  `rectifications.request`, tous les rôles par défaut — le pays voit
  l'erreur le premier), une seule demande en attente par ligne
  (contrainte `rectification_une_en_attente_par_ligne`) ; un
  administrateur **décide** (`POST /api/rectifications/{id}/approve/` ou
  `/refuse/ {note}`, `rectifications.decide` : `admin`, `super_admin`,
  jamais le pays) — **jamais l'auteur de la demande** (403), comme pour
  une réallocation. Approuvée, la ligne **revient en contrôle**
  (`in_review`), son `justified_amount` remis à zéro, son imputation
  conservée — elle reste déclarée et pèse toujours sur l'enveloppe, en
  engagé plutôt qu'en consommé — et le motif de la demande devient sa
  `control_note` ; le dossier, s'il avait été constaté (justifié, non
  justifié ou clôturé), revient en contrôle avec elle, ses notes
  intactes. Refusée, le constat tient ; le refus est motivé. La demande
  garde `previous_status` et `previous_justified_amount` ; `AuditLog`
  reçoit `rectification_requested`, `rectified` (sur la ligne, et sur le
  dossier qui la suit) et `rectification_decided` ; les administrateurs
  sont prévenus de la demande, le demandeur, le contrôle et — à
  l'approbation — le pays de la décision. `rectify` n'a pas de route sur
  la ligne : il ne se joue qu'en approuvant une demande
  (`transitions.approuver_rectification`). Verrous dans l'ordre du
  circuit : la demande, le dossier, puis la ligne. Une ligne qui a fait
  l'objet d'une demande **ne se retire plus**, même revenue au brouillon
  par une réouverture : elle a une histoire et la demande la référence
  (`transitions.exiger_une_ligne_jamais_rectifiee`, `allowed_actions`
  sans `delete`) ; elle se corrige et se resoumet.

**Une dépense soumise est irréversible** : elle ne revient pas au brouillon,
ne se modifie plus, ne se supprime pas. Seul un brouillon peut être retiré,
par son auteur, et ce retrait est journalisé. La réouverture et la
rectification sont les deux seules exceptions, et chacune est tracée,
motivée, à deux personnes et bornée comme ci-dessus. Le statut n'est jamais
modifiable par écriture de champ ; seules ces transitions le font évoluer,
et chacune écrit une entrée `AuditLog`.

### 5.5 bis `Rectification` — demande de rectification d'un constat

| Champ | Type | Notes |
|---|---|---|
| `expense` | FK → Expense (PROTECT) | la ligne contestée |
| `status` | Char(20) | `pending`, `approved`, `refused` |
| `motif` | Text | obligatoire |
| `requested_by`, `decided_by` | Char(180) | identités en texte (décision 10) |
| `decided_at` | DateTime (null) | contrainte `rectification_decision_datee` : une décision est datée |
| `decision_note` | Text | obligatoire au refus |
| `previous_status` | Char(20) | état de la ligne à la demande (`justified` ou `closed`) |
| `previous_justified_amount` | Decimal(16,2) | ce que l'approbation défait |

Ni modification ni suppression (`PUT`, `PATCH`, `DELETE` → 405) : un motif
changé après coup ferait mentir le journal. Périmètre : celui de la ligne
(`expense__country`, `expense__team`).

### 5.6 `AuditLog` — journal des actions sensibles

Consultable par `audit.read` (`admin`, `super_admin` par défaut) : la RH, qui
audite, et la direction. Le DM et le DF n'y accèdent pas — le journal relit
leurs décisions.

| Champ | Type | Notes |
|---|---|---|
| `user` | Char(180) | identité en texte |
| `action` | Char(32) | `created`, `updated`, `submitted`, `reviewed`, `justified`, `unjustified`, `approved` / `rejected` (contrôle d'une pièce), `deleted` (brouillon), `closed`, `reopened` (réouverture, avec le motif ; sur le dossier et sur chaque ligne), `rectification_requested`, `rectification_decided`, `rectified` (rectification d'un constat : la demande, la décision, la ligne et le dossier remis en contrôle, avec le motif et le montant justifié défait), `proof_uploaded`, `proof_replaced`, `proof_to_review`, `downloaded` (pièce, ou export avec `detail = {year, month, country, format}`), `imported` (Excel) |
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
| `kind` | Char(32) | `budget_threshold`, `budget_overrun`, `expense_submitted`, `expense_rejected`, `dossier_reopened` (aux comptes qui suivent le pays), `proof_missing`, `proof_incomplete`, `reallocation_requested`, `rectification_requested` (aux administrateurs), `rectification_decided` (au demandeur et au contrôle ; au pays aussi quand la ligne revient en contrôle), `storage_error` |
| `level` | Char | `info`, `warning`, `critical` |
| `title`, `body`, `link` | | |
| `country` | FK → Country (null) | |
| `dedup_key` | Char | évite de signaler deux fois le même franchissement |
| `read_at`, `emailed_at`, `created_at` | DateTime | |

Les alertes sont **calculées** à chaque lecture du tableau de bord ; seule
leur notification (`manage.py notify_alerts`, lancé par l'ordonnanceur)
écrit ces lignes et envoie les e-mails. Titre, corps et e-mail sont rendus
dans la langue du destinataire (`UserProfile.language`). Le rapport
périodique n'attache le classeur qu'à ceux qui exportent (`data.export`).

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

Les décisions **60 à 71** viennent toutes de l'audit de résilience de
septembre 2026 : ce qu'elles corrigent, comment cela a été mesuré et ce
qui reste non couvert sont dans [`audit-resilience.md`](audit-resilience.md).

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
| 18 | Rôles | **cinq** : `manager`, `dm`, `df`, `admin`, `super_admin`. Ni direction des opérations ni auditeur distincts. **Le DM et le DF n'ont aucun droit d'administration** (décision du produit) : ils ne sont ni administrateurs ni super administrateurs et gardent leurs seules fonctions de contrôle. Enveloppes, réallocations, taux de change et dépassements : `budgets.*`, `reallocations.*`, `rates.manage` = `admin`, `super_admin` (décision 58 ; `super_admin` seul jusque-là) ; journal d'audit, fichiers, réouverture : `admin`, `super_admin`. Ces défauts se règlent dans la matrice des droits (décision 43), sauf les verrous |
| 19 | Périmètre d'un manager | **ses équipes** (`UserProfile.teams`), vérifié sur le queryset (`CountryScopedMixin.team_lookup`) ; sans équipe rattachée, tout son pays. Les autres rôles ne sont pas restreints par équipe |
| 20 | Réouverture | **seule exception à l'irréversibilité** : `dossiers.reopen` (`admin`, `super_admin` par défaut, jamais le pays), motif obligatoire (`Dossier.reopen_note`), `AuditLog` `reopened` sur le dossier et ses lignes, lignes en brouillon sans imputation, **notification aux `manager` du pays** (ceux qui déclarent et doivent resoumettre), pas au `dm` ; refusée dès qu'une ligne est justifiée ou clôturée. Pour demander des comptes, jamais pour corriger en silence |
| 21 | Fichiers | import Excel et exports (`xlsx`, `csv`, `docx`, `pdf` ; `year`, `month` facultatif, `country`) **réservés à `data.export` / `data.import`** (`admin`, `super_admin` par défaut), lecture comprise ; tous les autres travaillent dans l'application. CSV UTF-8 avec BOM, séparateur `;` ; totaux à devise unique seulement. Chaque export est journalisé avec ses paramètres |
| 22 | Rétention | **illimitée** : aucune purge de dossier, pièce, journal ou notification ; les sauvegardes gardent une copie mensuelle pour toujours (`deploy/sauvegarder.sh`) |
| 23 | Authentification | **TOTP proposé, obligatoire seulement si `DJANGO_TOTP_REQUIRED`** (`totp_secret`, `totp_confirmed_at` ; politique exposée par `/api/me/` `totp_required`) — l'obligation est reportée par la direction, le code reste prêt ; réinitialisation par un administrateur seulement, tracée ; adresse e-mail dans `ALLOWED_EMAIL_DOMAINS` |
| 24 | Langue | **bilingue français / anglais** : `Accept-Language` côté API, préférence `language` sur le profil ; le français est la référence des messages, l'anglais vient du catalogue unique `backend/locale/en` (décision 42) ; notifications et e-mails dans la langue du destinataire |
| 25 | Supports | web et **application de bureau installable (PWA)** ; pas d'usage mobile prévu |
| 26 | Siège et pays | **le manager déclare, le DM contrôle, le DF constate.** Le `manager` est le seul compte de pays ; `dm` et `df` sont au siège. La mise en contrôle (`expenses.review`) et le constat (`expenses.validate`) sont deux capacités distinctes ; `admin` et `super_admin` ont les deux. La RH tient le référentiel de tous les pays, le manager celui du sien |
| 27 | Nom de compte | **`username` immuable** après création : les quatre yeux comparent sur lui, l'historique le cite en texte |
| 28 | Code TOTP | **à usage unique** (`totp_last_counter`) : un code accepté ne se rejoue pas, même dans sa fenêtre de validité |
| 29 | Périmètre par équipes | **administrable par l'API** (`teams`, `teams_detail` sur `/api/users/`), borné aux pays du compte, journalisé ; rôle et langue tracés quel que soit le chemin, admin Django compris |
| 30 | Back-office Django | `/admin/` **soumis aux mêmes verrous** que l'API (mot de passe provisoire, 2FA si exigée) et non routé depuis l'extérieur : ce n'est pas une voie de secours (`deploy/README.md`) |
| 31 | Export des dépenses | classé par **date de ligne** (plus par date de dossier) ; la période demandée est bornée dans le **fuseau du pays visé**, en UTC quand plusieurs pays sont lus ensemble |
| 32 | Notifications et alertes | `Notification.country` en **PROTECT** : un pays qui a des notifications ne se supprime pas (rien ne se supprime) ; chaque alerte du tableau de bord porte une clé `team`, pour que le manager lise les siennes |
| 33 | Quatre yeux | étendus à la **mise en contrôle et à la clôture**, sur la ligne et sur le dossier : celui qui a saisi ne prend aucune décision sur ce qu'il a saisi, fût-il au siège |
| 34 | Dossier : pays et équipe | le **pays est figé** dès que le dossier porte une ligne ou une pièce ; l'**équipe** l'est tant qu'une ligne porte une autre équipe. Une ligne porte l'équipe de son dossier ; un manager rattaché à des équipes doit en choisir une des siennes à la création |
| 35 | Décisions exposées | `allowed_actions` (ligne, dossier), `allowed_reviews` (pièce), `can_decide` (réallocation), **calculés côté serveur** : l'interface les lit et ne reproduit plus la matrice des rôles ; une transition de dossier renvoie le détail complet |
| 36 | Sauvegardes hors machine | **la copie hors machine des sauvegardes est obligatoire avant toute mise en production** : chaque dump réussi (quotidien et mensuel) et le miroir des pièces partent vers un stockage objet S3 chez un autre hébergeur ou dans une autre région (`SAUVEGARDE_DISTANT_*`, service `sauvegarde-distante`, `rclone`), sont vérifiés après envoi, et le journal dit « ✔ copie distante » ou « ✘ ». Sans distant configuré, la pile tourne mais le dit à chaque occasion ; la restauration depuis le distant (`restaurer.sh --depuis-distant`) est éprouvée avant la mise en production. Complète la décision 22 : la conservation illimitée ne vaut que si la copie survit au serveur (`deploy/README.md`, « Copie hors machine ») |
| 37 | Supervision | **profil Compose optionnel** (`supervision` : Prometheus, exporteurs, Grafana), désactivé par défaut et **activé quand l'exploitation le demande** (`SUPERVISION=1` dans `.env`) ; Caddy ne route `/grafana/` et l'interface ne montre l'entrée « Supervision » (drapeau `supervision` de `/api/configuration/`) que si le profil est actif. Les mesures ne sont pas des données métier : les activer ou non ne change rien à ce que la plateforme conserve (`deploy/README.md`, « Supervision ») |
| 38 | Journaux : une seule porte | **`core.journal.tracer(request, action, instance, famille=…)`** est la seule écriture des journaux. La famille choisit le journal : `referentiel`, `compte`, `configuration`, `session` vont dans `ChangeLog` ; `circuit`, `piece`, `fichier`, `import`, `export` dans `AuditLog`. Auteur, adresse (`core.requetes.client_ip`) et appareil se remplissent au même endroit ; `core.signals.journaliser`, `accounts.journal.journaliser_compte` et `expenses.audit.record` ne sont plus que des couches d'adaptation. Un test structurel (`core/tests/test_journal_unique.py`) refuse tout `AuditLog.objects.create` ou `ChangeLog.objects.create` hors de la façade |
| 39 | Cloisonnement : une seule primitive | **`accounts.perimetre.filtrer(queryset, access, pays=…, equipe=…)`** porte la règle — pays du compte, équipes du manager, une entité sans équipe (`team IS NULL`) échappe au manager cloisonné — et tout le reste lui délègue : `CountryScopedMixin`, `ChampCloisonne` (déplacé de `expenses` vers `accounts.perimetre`, avec `chemin_pays`, `chemin_equipe`, `distinct`), `Budget.objects.visible_par`, `reporting.scope.querysets_pour`. `PerimetreMixin` a disparu au profit de `ChampCloisonne`. `comptes_couvrant` en est la réciproque pour les notifications (qui voit un objet en est prévenu), vérifiée par un test. Les rôles structurels ne se déclarent que dans `accounts/models.py` (`HEADQUARTERS_ROLES`, `ALWAYS_GLOBAL_ROLES`) et `accounts/permissions.py` (`COUNTRY_ROLES`) ; les droits sont des capacités (décision 43) et `notifications.triggers.controleurs()`, `arbitres()`, `expenses.workflow.ACTION_CAPACITES` les lisent. Un test traversant (`accounts/tests/test_traversee.py`) parcourt chaque route du routeur avec un décor par pays et par équipe |
| 40 | Ordre des applications | **`core < accounts < notifications < budget < expenses < reporting`**, en tête de module, vérifié par `core/tests/test_dependances.py` (analyse `ast`, hors tests et migrations). Pour que `core` ne connaisse pas les comptes, l'authentification (`ThrottledObtainAuthToken`, limites de débit), le back-office (`BackOfficePermission`, `ConfigurationView`, `WorkflowConfigurationView`) et l'API du référentiel (`accounts/referentiel.py`) sont routés par `accounts.urls` — mêmes chemins, mêmes noms. Les états du circuit (`Status` et ses ensembles) vivent dans `core/statuts.py`, ré-exportés par `expenses.workflow`, pour que `budget` ne lise plus `expenses`. `notifications` vient avant `budget` et `expenses`, qui appellent ses déclencheurs : un service ne dépend pas de ceux qui l'appellent. Reste, assumé et commenté, un import paresseux : la devise de consolidation lue par la configuration |
| 41 | Règles du circuit : des services | **Les règles du circuit sont des services appelés par les vues, l'import et les commandes ; une vue ne porte que verrou HTTP (périmètre, rôle), sérialisation et réponse.** `expenses/transitions.py` — `soumettre`, `rouvrir`, `mettre_en_controle`, `trancher` (`justify`/`reject`), `cloturer`, `retirer_brouillon`, `controler_piece` — et `budget/transitions.py` — `demander`, `approuver`, `refuser` — prennent les verrous, vérifient l'état (`next_status`), la capacité (`ACTION_CAPACITES`, `reallocations.request`, `reallocations.decide`, via `exiger_la_capacite`), les quatre yeux (`workflow.breaks_four_eyes`, seul prédicat, partagé avec `allowed_actions`), les lignes exigées, l'imputation, la politique de dépassement, le disponible et l'absence d'auto-décision, puis journalisent via `core.journal.tracer` et notifient. Chaque service reçoit l'`Access` de l'acteur (qui porte désormais `username`) et une `core.journal.Trace` (`user`, `ip`, `user_agent`, `compte`), construite par la vue (`Trace.depuis_requete`) ou par une commande (`Trace.depuis_compte`), et rend un `Resultat` (`instance`, `warning`, `audit`). Un refus est une exception de `core/regles.py` — `RegleViolee(champ, message)` → 400, `PermissionRefusee` → 403, `HorsPerimetre` → 404 — que la vue traduit par `traduire_les_regles()` avec les messages d'avant ; `workflow.TransitionError` en est une sur `status`. Les réallocations sont journalisées dans `AuditLog` (famille `circuit`, actions `created`/`updated` avec `from_status`/`to_status`) en plus du `ChangeLog` des enveloppes ; `can_decide` lit `budget.transitions.peut_decider`. `seed_demo` passe par les services ; `notify_alerts` lit par `querysets_pour` avec un `Access` explicite (`SIEGE`) et ne transite rien ; l'import crée des brouillons, hors circuit. Tests unitaires sans HTTP : `expenses/tests/test_transitions.py`, `budget/tests/test_transitions.py` |
| 42 | Catalogues de traduction | **Un seul catalogue serveur**, `backend/locale/en/LC_MESSAGES/django.po` (`LOCALE_PATHS`), à la place des six catalogues d'application. Une chaîne n'a qu'un endroit où être traduite et la même traduction sert à toutes les apps — « Intitulé de dépenses », « Mise en contrôle », « Soumettre à approbation » divergeaient entre `core` et `expenses` ou `budget`. Une seule commande le régénère (`manage.py makemessages -l en --ignore=tests --no-obsolete`, références `#:` conservées, obsolètes retirés), une seule le compile (`django-admin compilemessages -l en`, dans l'image et au démarrage). Aucun `msgstr` vide ni `fuzzy` : la CI passe `makemessages`, `msgfmt --check`, puis `msgattrib --untranslated` et `--only-fuzzy`, et échoue dès qu'ils rendent quelque chose. Un faux format (`% e` dans « ({taux} % engagés) ») se neutralise à la source par `# xgettext:no-python-format`. Le `.mo` n'est jamais versionné |
| 43 | Matrice des droits configurable | **Chaque action de l'API est une capacité nommée `ressource.verbe`** (`CAPACITES`, 27 entrées en six groupes : comptes et administration, référentiel, enveloppes, déclaration, contrôle, fichiers), avec des rôles **par défaut** qui sont les décisions du produit. Une vue déclare `write_capability` / `action_write_capabilities` (et `read_capability` pour une lecture réservée), un service `exiger_la_capacite` ; plus aucun ensemble de rôles n'est figé dans une vue. **Les rôles effectifs viennent de la configuration** : `WorkflowConfiguration.capability_roles` (JSON, capacité → rôles, seulement pour ce qui s'écarte du défaut), réglé par les administrateurs dans « Configuration › Permissions » (`PATCH /api/permissions/`, `ChangeLog` famille `configuration`, libellé « Matrice des droits », diff par capacité) et appliqué à la requête suivante — vues, services, `allowed_actions`, notifications (`controleurs()`, `arbitres()`), rapport périodique. **Deux verrous ne se règlent pas et s'appliquent à la lecture** (`Capacite.roles_effectifs`), pas seulement à l'enregistrement : `fixes` (les administrateurs — `admin` et `super_admin` — ont tout, décision 58 ; `configuration.manage` est en outre verrouillée hors d'eux, ni élargie ni retirée) et `verrouillees` (le `manager` ne reçoit jamais le contrôle — `expenses.review`, `expenses.validate`, `expenses.close`, `proofs.review`, `dossiers.reopen` —, l'administration — `audit.read`, `countries.create`, `countries.update` — ni l'arbitrage — `budgets.*`, `reallocations.decide`, `rates.manage` ; et `users.*` ne s'ouvre qu'aux administrateurs, jamais à un rôle restrictible à des pays, qui pourrait sinon se créer un administrateur). Le référentiel (`referentiel.*`) et la demande de réallocation restent ouvrables au pays : ce sont des choix d'organisation, tracés. La matrice résolue est mémorisée au niveau du module avec l'empreinte du choix (`charger()` rend une instance neuve à chaque appel, un mémo sur l'instance ne servirait à rien). Côté client, `allowed_actions` porte aussi la saisie (`edit`, `add_line`, `upload`, `delete`, calculées par `workflow.peut_saisir` : brouillon, auteur, capacité) : les constantes `LOCKED_STATUSES`, `DELETABLE_STATUSES`, `PROOF_LOCKED_STATUSES` ont disparu du client. Tests : `accounts/tests/test_matrice_des_droits.py`, `expenses/tests/test_actions_autorisees.py` (`ActionsDeSaisieTests`) |
| 44 | Admin Django en développement seul | **`/admin/` n'est monté que si `ADMIN_ENABLED` (= `DEBUG`, vrai sous test).** En production nginx ne le relayait déjà pas ; mais une session ouverte sur `/admin/login/` avec le seul mot de passe authentifiait aussi l'API (`SessionAuthentication`) et contournait le second facteur d'un compte enrôlé. Tout ce que l'admin offrait a son équivalent dans l'API et le back-office de l'application ; l'admin reste un outil de développement, soumis aux mêmes verrous (`accounts.middleware`), et, pour les lignes, dossiers et pièces, **en lecture seule dès qu'ils sont déclarés** (`expenses/admin.py`, `BrouillonSeulementMixin` ; fichier, dossier et nom d'une pièce figés ; aucun bénéficiaire supprimable) |
| 45 | Pièces : le contenu confirme l'extension | **Les premiers octets d'un justificatif doivent correspondre à son extension** (`expenses/serializers.py`, `SIGNATURES` : `%PDF`, en-têtes JPEG/PNG/WebP/HEIC/OLE/ZIP, texte sans octet nul ni balise HTML) et **le type MIME enregistré vient de cette table, jamais de l'en-tête du client**. Un HTML nommé `recu.pdf` était sinon stocké puis rejoué dans l'aperçu du siège, dans l'origine de l'application. **Le doublon d'une pièce est tranché en base** : contrainte d'unicité partielle `(dossier, sha256)` pour les premières versions (`piece_unique_par_dossier`), parce que deux dépôts simultanés passaient tous deux la vérification du sérialiseur ; le remplacement explicite garde le droit de redéposer le même contenu. Un classeur importé est aussi borné **une fois décompressé** (5 × `MAX_PROOF_SIZE`), `zipfile` avant openpyxl. Tests : `test_contenu_des_pieces.py`, `test_verrous.py` (dépôt simultané), `test_import.py` (`ClasseurGonfleTests`) |
| 46 | Brouillon : son auteur ou le siège | **Un brouillon se modifie par celui qui l'a saisi ou par le siège, jamais par un collègue du pays** (`transitions.exiger_l_auteur_du_brouillon`, appliqué par les vues de dossier et de ligne ; `allowed_actions` le reflète par `workflow.peut_saisir`). Un collègue qui changeait le montant laissait l'auteur soumettre, sous son nom, une ligne qu'il n'avait pas écrite. Le siège corrige à découvert : chaque modification est journalisée avec avant et après. Le retrait, lui, reste à l'auteur seul (décision 41) |
| 47 | Ce qui ne se règle ni ne se réécrit | **L'argent se réglait par la direction seule** : `budgets.*`, `reallocations.*`, `rates.manage` portaient `reglable_par = super_admin` (`Capacite.reglable_par`, exposé `settable_by_roles`) — règle levée par la décision 58, qui ouvre ces lignes à l'administrateur ; le mécanisme `reglable_par` reste, uniforme (`admin`, `super_admin`). **Une réallocation ne se réécrit pas** : ni `PUT` ni `PATCH` (405), elle se demande puis s'approuve ou se refuse, sinon le montant enregistré ne serait plus celui du mouvement exécuté. **Le référentiel du pays voisin n'existe pas pour le demandeur** : `owner`, `project`, `expense_title`, `marketing_category`, `beneficiary` sont des `ChampCloisonne`, un identifiant voisin répond comme un identifiant inconnu. **Le débit nginx se compte par adresse cliente seulement** (`$binary_remote_addr`, adresse réelle rétablie depuis les seuls mandataires de confiance) : la clé fut un temps le jeton (`$http_authorization`), qu'un en-tête inventé à chaque requête rendait neuf à chaque fois — la limite ne s'appliquait plus (audit §4.6). Le point de santé, qui interroge la base sans compte, a sa propre limite serrée, côté nginx et côté Django (`HealthRateThrottle`). **Le changement de mot de passe a sa limite** (`password`, 10/min) : le porteur d'un jeton volé ne devine pas le mot de passe courant à la volée. Tests : `test_matrice_des_droits.py`, `test_budgets.py` (`test_une_reallocation_ne_se_reecrit_pas`), `test_cloisonnement_referentiel.py`, `test_protection_connexion.py`, `test_comptes.py` (`LimiteDuMotDePasseTests`) |
| 48 | Hébergement : serveur dédié, Railway en repli | **La plateforme tourne sur le serveur Hetzner, sous le domaine gratuit `178-105-215-49.sslip.io`** — le groupe n'a pas de nom de domaine, et Railway, d'abord retenu, refuse la carte prépayée qui sert aux paiements du groupe. Railway reste une voie de repli prête (`docs/deploiement-railway.md`). Trois services construits depuis le dépôt (`backend`, `scheduler`, `frontend`), la base Postgres et un Bucket S3 fournis par Railway ; TLS et domaine `*.up.railway.app` par Railway, qui remplace Caddy. Le code ne change pas de forme : `PORT` est honoré, `frontend/nginx.conf` devient un gabarit rempli au démarrage (`NGINX_*`), la pile `deploy/` reste entière pour le jour d'un serveur (`DEPLOIEMENT_SSH=1`). Ce qu'on perd et doit organiser autrement : les sauvegardes (celles de Railway pour la base, un miroir du Bucket à mettre en place avant d'ouvrir aux pays) et la supervision Grafana. |
| 49 | Une écriture et sa trace, ensemble ; l'e-mail après | **Chaque `create` et `update` de l'API tient dans une seule transaction** (`core.mixins.NoDestroyModelViewSet`) : `serializer.save()` commitait puis la trace (`AuditLog` par la vue, `ChangeLog` par les signaux en `pre_save`) s'écrivait à part — une trace impossible laissait la modification sans trace, et l'historique attestait d'un mouvement que l'écriture suivante pouvait ne jamais faire. Le choix est fait à la porte des vues d'écriture, pas par `ATOMIC_REQUESTS` : lectures, exports en flux et téléchargements n'ont rien à faire dans une transaction. **La notification in-app est écrite dans la transaction de l'action, sous un point de reprise** (`notifications.triggers._safe`) : une erreur de base dans la notification — un titre trop long pour sa colonne — laissait la transaction avortée, l'exception avalée ne disait rien à Django, qui commitait une transaction que PostgreSQL avait déjà annulée ; la transition et sa trace disparaissaient, l'API répondait 200. `Notification.title` passe à 500 caractères (`TITRE_MAX`, le pire cas composé est testé), les libellés ne sont jamais tronqués. **L'e-mail part après la validation de la transaction** (`transaction.on_commit`, `robust=True`), hors de tout verrou métier — un serveur de courrier lent bloquait l'enveloppe du pays le temps des envois. `on_commit` ne garantit pas la livraison : la ligne elle-même (`emailed_at` vide, `email_attempted_at`, `email_attempts`) est l'enregistrement durable du travail restant, repris par l'ordonnanceur (`envoyer_emails`, `SCHEDULE_EMAILS`, cinq minutes) jusqu'à cinq essais, sur les notifications de moins de trois jours ; `emailed_at` n'est posé qu'après `send()`, et chaque message est marqué un par un. Tests : `notifications/tests/test_reprise_des_emails.py`, `expenses/tests/test_atomicite.py` |
| 50 | Aucun fichier ne se perd | **Rien ne s'efface dans une transaction.** Un stockage objet n'a pas de retour arrière : `piece.file.delete()` dans la transaction du retrait d'un brouillon laissait, si la base la défaisait ensuite (`ProtectedError` sur une ligne arrivée entre-temps), des fiches sans leurs fichiers. La demande d'effacement est enregistrée dans la transaction (`FichierASupprimer` : chemin, empreinte, dossier, demandeur — la ligne reste et atteste), exécutée après le commit (`expenses.stockage.programmer_la_suppression`, `on_commit`), reprise par l'ordonnanceur (`supprimer_fichiers`, `SCHEDULE_SUPPRESSIONS`, dix essais) et refusée si une fiche référence encore le fichier. Les lignes et les pièces d'un brouillon retiré sont lues sous verrou, `ProtectedError` devient un 400 lisible. **Un dépôt refusé ne laisse pas d'orphelin** : `ProofSerializer.create` retire le fichier écrit par `FileField` avant l'`INSERT` que la contrainte a refusé. **L'inventaire des orphelins n'efface rien** (`pieces_orphelines`, délai de sécurité 24 h, demandes en attente exclues). **La trace `downloaded` dit « servi », pas « reçu »** : le fichier est ouvert avant que la trace ne s'écrive ; un objet absent répond 503 sans trace. Tests : `expenses/tests/test_stockage.py` |
| 51 | Sauvegardes chiffrées, ineffaçables depuis le serveur, vérifiées chaque matin, restauration prouvée | **Rien ne part en clair hors de la machine** : la copie distante passe par un coffre rclone (`crypt`, `SAUVEGARDE_CHIFFREMENT_CLE` en secret Compose, noms en clair, contenu chiffré, vérification par `cryptcheck`) — un dump contient les jetons de session et les secrets TOTP en clair, et le distant est chez un tiers ; sans clé, rien ne part. La clé se garde aussi hors du serveur. **Le serveur n'efface rien sur le distant** (`SAUVEGARDE_DISTANT_ROTATION=0`, clé sans droit de suppression, rétention par règle de cycle de vie du bucket, versions conservées) : un serveur compromis n'emporte pas les sauvegardes. **Backblaze B2** retenu (10 Go gratuits, sans carte). **Une sauvegarde qui manque se dit** : marqueurs `.derniere-reussite-*` écrits par `sauvegarder.sh`, lus chaque matin par `verifier_sauvegardes` (ordonnanceur, volume monté en lecture seule), notification critique aux administrateurs au-delà de 26 h. **Objectifs** : perte maximale 24 h, reprise 4 h. **La restauration se prouve** dans une pile jetable, courrier en console, avec `verifier_restauration` (décomptes, dernière trace d'audit, chaque pièce ouverte et son empreinte comparée) et un compte rendu daté ; après toute restauration de la pile, `revoquer_sessions --tous` — une base d'une autre date réactive les accès révoqués depuis. **Ce qu'une fuite permet** est distingué (deploy/README.md, « Après une fuite ») : un jeton entre sans mot de passe ni second facteur ; un secret TOTP ne calcule que le second facteur. Tests : `reporting/tests/test_sauvegardes.py` |
| 52 | La livraison ne peut que livrer | **La clé SSH de livraison n'a qu'une commande** (`justi-livrer`, forcée par `authorized_keys`, `sudo` restreint à elle seule) : elle demande le déploiement d'une étiquette, dont chaque valeur est revérifiée sur le serveur ; `deploy` n'est plus dans le groupe `docker` (qui vaut root), le répertoire d'exploitation et le `.env` appartiennent à root, la CI ne copie plus rien sur le serveur — les fichiers de `deploy/` se mettent à jour en root, à la main. Quiconque pousse sur `main` n'exécute plus de code en root. **Les actions GitHub sont épinglées par SHA** (Dependabot les suit), une règle de protection de `main` exige une pull request verte. Migration d'un serveur en service : `durcir_livraison.sh`, avec vérification et retour arrière (deploy/README.md, « Réduire les pouvoirs de la livraison ») |
| 53 | L'état qui compte est celui du verrou | **Les vues de modification relisent l'objet sous verrou avant d'écrire** (`transitions.verrouiller`, `exiger_un_brouillon`) : le sérialiseur vérifiait « encore en brouillon » sur une instance lue sans verrou, et `save()` réécrivait ensuite toutes les colonnes de cette instance périmée — une soumission passée entre-temps était défaite, la ligne revenait au brouillon sans imputation, sans réouverture, sans trace (audit du 8 septembre 2026, §3.6). Ordre des verrous partout le même : le dossier, puis la ligne, comme la soumission. La création d'une ligne ou d'une pièce verrouille le dossier visé : un retrait ou une soumission au même instant attend, puis l'écriture trouve l'état vrai (404 si le dossier n'est plus). **Une ligne importée a une identité** (`Expense.import_key`, empreinte jour-libellé-montant, contrainte `ligne_importee_unique_par_dossier`, partielle : les lignes saisies n'en ont pas) et l'import relit le dossier sous verrou avant d'écrire (§3.7) ; `doublons_importes` inventorie sans supprimer. Tests : `expenses/tests/test_verrous.py` (`CourseSurLaSaisie`, `CourseSurLImport`), à deux connexions réelles |
| 54 | Règles de calcul, une seule fois | **Les mêmes règles pour l'API, les écrans, les exports et les rapports** (`budget/aggregates.py`, en tête de module) : engagé = soumis ou en contrôle ; consommé = justifié, non justifié ou clôturé ; **un brouillon ne compte nulle part** — la ligne TOTAL de l'export des dépenses l'exclut désormais, comme l'écran ; attribué d'un pays = son enveloppe de pays, **à défaut la somme de ses sous-enveloppes** (un attribué à zéro donnait un disponible négatif) ; disponible = attribué − consommé − engagé. **Un exercice se consolide aux taux en vigueur à sa date de référence** (`date_de_reference` : le 31 décembre d'un exercice clos, ce jour pour l'exercice en cours), partout — `/api/budgets/summary/`, `/api/dashboard/`, la liste des enveloppes (chaque exercice à sa date), le rapport périodique. **Les taux se publient dans l'ordre du temps et ne se modifient pas** (`ExchangeRateSerializer`) : le taux « au 31 décembre 2024 » est acquis pour toujours, et un rapport sur 2024 donne le même chiffre en 2026 qu'en 2025 ; une erreur se corrige par un nouveau taux daté du jour. **La revalorisation** — relire un exercice clos aux taux d'aujourd'hui — est un autre calcul, demandé explicitement (`manage.py consolidation --taux-du-jour`), jamais celui des écrans. **Une enveloppe ne se désactive pas tant qu'elle porte des lignes déclarées** : désactivée, elle sortait du suivi et son consommé disparaissait d'un écran sans disparaître de l'autre. **Un taux croisé s'applique exact** (montant × taux source ÷ taux cible, arrondi au centime à la fin) ; le taux figé sur la ligne, à six décimales, est indicatif — vers le FCFA les deux coïncident. Tests : `budget/tests/test_chiffres.py`, `reporting/tests/test_exports.py` |
| 55 | Protections de l'API resserrées | **La limite anti-bourrage ne se contourne plus avec un jeton** : `ThrottledObtainAuthToken` n'authentifie plus rien (`authentication_classes = []`) et `LoginRateThrottle` dérive de `SimpleRateThrottle`, comptant toujours par adresse — un jeton valide dans l'en-tête levait la limite `AnonRateThrottle` et permettait de pulvériser un mot de passe sur tous les comptes (audit §3.5). Le **référentiel de `core`** (équipes, projets, centres de coûts, intitulés, catégories, bénéficiaires) passe par `ChampCloisonne` (`accounts.referentiel._cloisonne`, `BeneficiarySerializer`) : un pays hors périmètre est un pays inconnu, et le validateur d'unicité `(country, nom)` ne trahit plus l'existence d'une entité voisine par la différence entre 400 « existe déjà » et 403 « hors périmètre » (§4.5). Le **point de santé** (`/api/health/`), qui exécute un `SELECT`, a sa limite par adresse (`HealthRateThrottle`, et une zone nginx dédiée) : il n'est plus un amplificateur anonyme (§4.6). Un **code TOTP non-ASCII** (`.isdigit()` vrai, `compare_digest` en exception) ne provoque plus de 500 (`compteur_du_code`, garde `isascii()`). Tests : `accounts/tests/test_protection_connexion.py`, `accounts/tests/test_cloisonnement_referentiel.py` |
| 56 | Chiffrement : ce qui est protégé de quoi | **Le volume `sauvegardes` du serveur reste en clair** par défaut : `rclone crypt` chiffre ce qu'il **envoie**, pas ce qui reste sur la machine. La copie distante, elle, est chiffrée (le tiers ne lit rien), noms de fichiers en clair pour `--lister`/`--rapatrier`. Le secret est **symétrique et présent sur le serveur** — « clé hors serveur » désigne une **copie de récupération** gardée ailleurs, pas un serveur qui en serait dépourvu : le serveur peut relire sa propre copie distante. À conserver pour restaurer : la clé, **le sel** (second mot de passe du coffre) et les réglages du coffre. **Pour que le serveur ne puisse pas déchiffrer**, `SAUVEGARDE_CLE_PUBLIQUE` chiffre chaque dump à la sortie de `pg_dump` avec une clé publique (`openssl smime`, AES-256, suffixe `.enc`) : le dump n'existe en clair nulle part et la clé privée reste hors machine ; `restaurer.sh` refuse un `.enc` en rappelant la commande de déchiffrement. Les copies **déjà envoyées en clair** ne se chiffrent pas rétroactivement : à supprimer depuis la console du fournisseur, puis copie complète. Tests exécutés : `deploy/tests/test_sauvegarder.sh` (39 contrôles, doublures de `pg_dump`/`mc`/`rclone`, vrai `openssl`), joué par la CI (travail « Exploitation ») |
| 57 | Rectification d'un constat | **Seconde exception à l'irréversibilité**, là où la réouverture s'arrête (§5.5, `Rectification`) : une ligne justifiée ou clôturée à tort se **demande** à rectifier — n'importe quel rôle, motif obligatoire, une demande en attente par ligne — et un **administrateur qui n'est pas le demandeur** approuve ou refuse (`rectifications.request` = tous, `rectifications.decide` = `admin`, `super_admin`, verrouillée hors du pays). Approuvée, la ligne **revient en contrôle** — jamais au brouillon : la dépense reste déclarée, imputée, en engagé — montant justifié à zéro, motif en `control_note`, et le dossier constaté la suit ; l'état et le montant défaits restent sur la demande et dans `AuditLog` (`rectification_requested`, `rectified`, `rectification_decided`). Aucune route `rectify` : le constat ne se défait qu'en approuvant une demande. Une ligne contestée un jour ne se retire plus, même rouverte au brouillon — elle se corrige et se resoumet. Tests : `expenses/tests/test_rectification.py` |
| 58 | L'administrateur a tous les droits, et les attribue | **`admin` = `super_admin` dans la matrice** (demande du produit, 11/09/2026) : les deux rôles sont `fixes` sur chaque capacité — personne ne peut leur retirer un droit, pas même l'autre — et `reglable_par` sur chaque ligne, l'argent compris : `budgets.create`, `budgets.update`, `reallocations.request`, `reallocations.decide`, `rates.manage` passent par défaut à `admin`, `super_admin` (ils étaient à `super_admin` seul, décisions 18 et 47). L'administrateur attribue ainsi chaque droit à n'importe quel rôle, dans les seules limites des verrous du pays (`_JAMAIS_LE_PAYS`) et des comptes (`_JAMAIS_HORS_ADMINISTRATEURS`), qui restent. Les deux rôles subsistent pour dire qui est RH et qui est direction, pas pour séparer des droits. Les notifications suivent la matrice (`arbitres()` prévient désormais les administrateurs d'une réallocation). Tests : `accounts/tests/test_matrice_des_droits.py` (`test_l_administrateur_a_l_argent_et_le_regle`, `test_les_administrateurs_gardent_tout`), `budget/tests/test_budgets.py` |
| 59 | Un chiffre affiché vient du serveur, jusqu'au dernier | **`unallocated` est publié par `CountryBudgetRow`** (`budget/aggregates.py`, `budget/serializers.py`) : la part de l'enveloppe d'un pays qui n'est pas encore découpée en sous-enveloppes. L'interface la déduisait d'`allocated - sub_allocated` — dernier montant de gestion calculé côté client, contre la règle « rien ne se calcule dans l'interface ». Le risque n'était pas l'arrondi (deux décimales le couvrent) mais la **divergence silencieuse** : le jour où `sub_allocated` change de définition — les enveloppes inactives comptées ou non —, l'écran mentirait sans que rien ne le signale. Le champ n'est **pas borné à zéro** : un négatif dit que les sous-enveloppes dépassent l'enveloppe du pays, fait qu'il faut voir. Même raison pour le **dépassement** du Pilotage, qui se mesurait sur le seul consommé quand le serveur compte `consumed + engaged` : l'écran affichait 120 % en corail à côté d'une barre sans débordement. Tests : `budget/tests/test_chiffres.py` (`NonRepartiTests`), `frontend/src/components/ui/charts.test.tsx` |
| 60 | Le stockage ne bloque pas ce qui ne le concerne pas | **Le client S3 porte des délais bornés** (`client_config` dans `config.settings` : `AWS_S3_CONNECT_TIMEOUT` 3 s, `AWS_S3_READ_TIMEOUT` 10 s, `AWS_S3_MAX_ATTEMPTS` 2). Sans eux, botocore attend soixante secondes par tentative et recommence jusqu'à cinq fois. Un audit de résilience l'a mesuré : un stockage qui accepte la connexion sans jamais répondre — un pare-feu qui avale les paquets, pas un service arrêté — prenait les huit threads de gunicorn et rendait **toute** l'API muette, y compris les écrans qui ne touchent aucun fichier ; sans reprise, et sans une ligne de journal. Le `--timeout` de gunicorn ne rattrape rien : en mode `gthread` il surveille la boucle du worker, pas ses threads de requête. Après correction, le téléchargement rend 503 en trente secondes et le reste de l'API répond en vingt millisecondes pendant la panne. Tests : `config/tests/test_delais_stockage.py` |
| 61 | Une panne laisse une trace, et cette trace a un nom | **`LOGGING` est défini** (`config.settings`), avec une seule sortie : la sortie standard, là où `docker compose logs` et tout collecteur vont chercher. Django n'a pas de configuration utilisable hors mode debug : son gestionnaire console porte le filtre `RequireDebugTrue` et celui par courriel n'écrit nulle part sans `ADMINS`. L'audit de résilience l'a mesuré — pendant une coupure de la base, **six mille erreurs 500 n'ont produit aucune ligne** ; restait le code d'état dans le journal d'accès de gunicorn, et rien pour dire pourquoi. Chaque ligne porte désormais `requete=`, `compte=` et `ip=` (`core.journalisation.FiltreContexte`), en `clé=valeur` : lisible dans un terminal et filtrable au `grep`. L'identifiant de requête part aussi en en-tête `X-Requete-Id`, pour qu'un utilisateur qui signale un incident puisse le citer ; un identifiant venu d'un mandataire n'est repris que s'il est inoffensif, un saut de ligne forgerait une seconde ligne de journal. Le filtre **ne résout jamais** `request.user` : le forcer interrogerait la base, et journaliser une panne de base provoquerait une panne de base. Tests : `core/tests/test_journalisation.py` |
| 62 | Une panne se dit en JSON, et du même code partout | **L'API ne rend plus de HTML** : `handler400` à `handler500` (`config/urls.py` → `core.exceptions`) répondent `{"detail": …}` sous `/api/` et à qui demande du JSON ; l'admin Django, monté en développement, garde ses pages. Un client qui faisait `response.json()` cassait *en plus* de l'erreur initiale. **Et une base injoignable rend 503 avec `Retry-After`, plus 500** (`EXCEPTION_HANDLER` de DRF) : un 500 se signale à un développeur, un 503 se retente tout seul. L'audit de résilience avait mesuré une incohérence — `/api/health/` rendait 503 pendant que `/api/dossiers/` rendait 500, pour une seule et même base coupée : le verrou d'accès (`accounts/middleware.py`) interroge la base dans un `process_view`, hors du champ de DRF, et Django y transforme l'exception en réponse avant qu'aucun middleware supérieur ne puisse la voir. Il attrape donc sa propre panne, avec la même définition (`core.exceptions.reponse_indisponible`). Un défaut réel reste une 500 : `gestionnaire_d_exception` rend `None` pour ce qu'il ne connaît pas, DRF relance, et la trace part dans le journal (décision 61). Tests : `core/tests/test_erreurs_json.py` |
| 63 | Une panne ne doit pas effacer les journaux qui l'expliquent | **Le débit des lignes « base injoignable » est borné** (`core.exceptions` : trace complète au plus toutes les `DJANGO_LOG_PANNE_TRACE` secondes, ligne compacte au plus toutes les `DJANGO_LOG_PANNE_RESUME`), et **la ligne que Django ajoute pour chaque réponse 503 est écartée** (`core.journalisation.SansDegradationRepetee`). Une base coupée fait échouer toutes les requêtes, et vite : le débit *monte* — 53 req/s en bon état, 307 en panne. Avec une trace de 7,8 ko par erreur, l'audit a mesuré **24 Mo en sept secondes** ; Docker retenant 100 Mo par service (`max-size` × `max-file`), une demi-minute de panne effaçait tout l'historique, y compris les lignes d'avant la panne. Le même test produit désormais **17,8 ko et seize lignes**, chacune avec son `requete=`. Rien d'utile n'est perdu : la trace est identique à chaque fois, et le nombre d'appels échoués est dit. Les 500 ne sont pas touchées — un défaut réel garde sa ligne et sa trace. Tests : `core/tests/test_erreurs_json.py`, `core/tests/test_journalisation.py` |
| 64 | Une livraison ne doit pas couper le travail en cours | **`stop_grace_period` est déclaré** sur `backend` (35 s) et `db` (30 s) dans `deploy/docker-compose.prod.yml`. Trois délais se contredisaient : `GUNICORN_TIMEOUT` à 120 s — parce qu'un export d'année complète ou une pièce de 20 Mo sur liaison lente dépassent 30 s —, `--graceful-timeout 30` pour vider les requêtes en vol, et **dix secondes** accordées par Compose faute de réglage. L'audit de résilience l'a mesuré : une pièce en cours de dépôt a mis **11,07 s** à finir après le SIGTERM au maître gunicorn, une seconde de trop — à chaque livraison, le déposant perdait son envoi. Aucune donnée n'était corrompue (les transitions sont atomiques, six SIGKILL en pleine écriture l'ont vérifié) ; le travail de la personne, si. L'ordonnanceur reste au défaut, délibérément : ses tâches sont des reprises, un arrêt brutal les laisse au prochain passage. Tests : `core/tests/test_arret_de_la_pile.py` |
| 65 | Ce qui ne partira plus doit se dire | **`envoyer_les_emails` signale les notifications abandonnées** (`notifications.services.abandonnees`, journal `WARNING` et sortie de la commande). Le journal écrivait « N e-mail(s) à reprendre » à chaque échec, puis se taisait : une fois `ESSAIS_MAX` atteint les lignes cessaient d'être réclamées, sans un mot — la dernière chose écrite était donc **fausse**, et l'exploitant croyait la reprise en cours. L'audit de résilience l'a mesuré : serveur de courrier arrêté, soixante notifications abandonnées après cinq passages, aucune trace. Le message dit aussi que **les notifications restent lisibles dans l'application** — rien n'est perdu, seule la relance par courriel l'est —, sans quoi l'avertissement paraîtrait plus grave qu'il n'est. Il s'éteint de lui-même après `AGE_MAX_DE_REPRISE` plutôt que de se répéter à chaque passage, et le chemin appelé après le commit d'une action ne le déclenche pas : il sert une requête, pas la supervision. Tests : `notifications/tests/test_reprise_des_emails.py` (`AbandonsSignalesTests`) |
| 66 | Le plafond de connexions est une décision, pas un défaut | **`max_connections` est fixé dans la pile** (`deploy/docker-compose.prod.yml`, `POSTGRES_MAX_CONNECTIONS`, 50 par défaut) et le budget est écrit là où l'exploitant règle les processus (`deploy/.env.example`). Postgres en laissait 100, un plafond que personne n'avait choisi et que le `mem_limit: 1g` de la base ne peut pas honorer : l'audit de résilience a mesuré **1,9 à 2,4 Mo par connexion**, plus 4 Mo par tri — cent connexions en train de trier feraient tuer la base par le noyau, une panne bien pire qu'un refus de connexion. Le même audit a établi que le serveur ouvre **exactement `GUNICORN_WORKERS × GUNICORN_THREADS`** connexions, jamais davantage : il n'y a pas de réserve qui grossit, la borne est structurelle — et donc **aucun besoin d'un gestionnaire de connexions** (pgbouncer résoudrait un problème que cette architecture n'a pas). Mesuré aussi : base pleine, le serveur **n'est pas la victime** — il garde ses connexions et a servi 1015 requêtes sans une erreur ; c'est **l'ordonnanceur** qui est refusé, parce qu'il partage le rôle applicatif, tandis que la sauvegarde et une session de dépannage gardent les trois places que Postgres réserve au propriétaire (`creer_role_applicatif.sql` crée le rôle du service en `NOSUPERUSER`, ce qui rend cette réserve effective). L'ordonnanceur refusé ne meurt pas et ne boucle pas : chaque tâche journalise sa cause exacte (décision 61) et repart au passage suivant. Son battement de cœur, lui, ne touche pas la base : le conteneur reste **sain** pendant que ses tâches échouent — c'est voulu, une sonde qui interroge la base ferait redémarrer l'ordonnanceur en boucle à chaque hoquet ; la surveillance de ses tâches passe par le journal. Tests : `core/tests/test_budget_de_connexions.py` |
| 67 | Les relations d'une ligne se préchargent, elles ne se joignent pas | **`ExpenseQuerySet.avec_les_relations`** remplace le `select_related` sur les douze relations de `EXPENSE_RELATIONS`, aux trois endroits qui l'appliquaient (liste et registre, détail d'un dossier, lecture sous verrou). Un `EXPLAIN (ANALYZE)` sur `/api/expenses/` a montré l'inattendu : la requête coûtait **91 ms de planification pour 43 ms d'exécution** — le planificateur coûtait plus du double de l'exécution, et Postgres recommençait à chaque appel, Django ne préparant aucune requête (`prepare_threshold` vaut `None`). Le coût suit le nombre de relations, pas le nombre de lignes : 0,6 ms à trois relations, 60 ms à neuf, **91 ms à quatorze** — et le même prix pour lire une seule ligne. Ni `geqo`, ni `geqo_threshold`, ni les limites de collapse n'y changent quoi que ce soit ; les relever est pire (890 ms, et 9,8 s sans `geqo`), et `join_collapse_limit = 1`, qui ramènerait la planification à 6 ms, **dégrade `/api/budgets/` de 9,6 à 22,7 ms** : un réglage global rend le planificateur aveugle partout, on ne l'a donc pas touché. Le préchargement pose une requête par relation, triviale, et leur nombre ne dépend pas de la page — dix-neuf pour vingt-cinq lignes comme pour deux cents. Mesuré sur 6 009 lignes : SQL cumulé d'une page **140 ms → 9 ms**, détail d'une ligne 17 → 4 ms, verrou tenu par `_verrouiller_la_ligne` **15,0 → 8,5 ms** malgré neuf requêtes au lieu d'une, et sur le serveur réel **22,4 → 49,1 req/s**, P95 470 → 286 ms. Le corps des réponses est identique, octet pour octet, sur les cinq chemins vérifiés. Les neuf allers-retours supplémentaires coûtent 0,8 ms : même avec un réseau dix fois plus lent, le choix tient. Ce n'est pas un N+1 — le nombre de requêtes est constant, et `QueryCountTests` le garde ; le nouveau test garde l'autre bout, la largeur de la jointure. Tests : `expenses/tests/test_queries.py` (`RelationsSansJointureTests`) |
| 68 | Une limite qui protège doit compter juste | **`core.debit.ComptageSansPerte`** sérialise le compteur des limites de connexion et de mot de passe (`LoginRateThrottle`, `LoginUsernameThrottle`, `PasswordRateThrottle`), par un verrou consultatif Postgres pris sur la clé. `SimpleRateThrottle` de DRF lit l'historique, y ajoute l'instant courant et réécrit le tout, sans verrou : deux requêtes simultanées lisent le même historique et la dernière écriture efface l'autre. L'audit de résilience l'a mesuré sur la limite de cinq essais par compte — **5 en séquentiel, 7 sur quatre fils, 11 sur huit, 13 sur seize**. La fuite suit le parallélisme du serveur : relever `GUNICORN_THREADS` affaiblissait la protection contre le bourrage d'identifiants, sans que rien ne le dise. Après correction : **exactement 5**, sur quarante tentatives lancées ensemble, trois fois de suite ; le séquentiel est inchangé et une connexion coûte toujours 678 ms, dominées par le hachage du mot de passe. La limite générale (`user`, 2000/heure) **n'est pas verrouillée** : elle ne défend rien — elle borne un client emballé —, et la sérialiser ferait attendre chaque requête d'un même compte derrière la précédente, pour aucun gain. `ScopedRateThrottle` a cédé la place à une classe explicite : elle ne servait qu'à lire l'échelle sur la vue. Tests : `accounts/tests/test_protection_connexion.py` (`CourseSurLaLimiteTests`, où la course est **forcée** — un test qui espère un entrelacement passe parfois sur du code fautif) |
| 69 | Le cache ne doit pas purger ce qui protège | **`CACHE_MAX_ENTRIES` est déclaré** (`config.settings`, `DJANGO_CACHE_MAX_ENTRIES`, 2000 par défaut). `DatabaseCache` purge sa table dès qu'elle dépasse `MAX_ENTRIES` — **300 par défaut**, jamais choisi — et supprime **par ordre alphabétique de clé, pas par ancienneté** (`_cull`, `cache_key_culling_sql`). Les compteurs anti-bourrage s'appellent `throttle_login_<adresse>` : ils se classent parmi les plus bas et partent donc les premiers. L'audit de résilience l'a mesuré : à **250 comptes actifs dans l'heure le compteur survit, à 400 il est effacé** — sans attaquant, par la seule croissance de la plateforme, chaque compte actif laissant une clé pendant une heure. Cela ferme le cas accidentel ; cela ne rend pas la limite insensible à un remplissage délibéré venu de nombreuses adresses, chaque nom de compte essayé créant une clé — mais un tel remplissage demande aujourd'hui une quarantaine d'adresses, la limite par adresse étant redevenue exacte (décision 68). Mesuré aussi, et laissé tel quel : la limitation de débit écrit à chaque lecture — **1,5 ko de journal d'écriture par `GET`** (4,2 ko si l'historique atteint mille entrées), et la table du cache pèse 1 576 ko pour 57 ko utiles. C'est le prix de l'algorithme de DRF ; le remplacer pour la limite générale coûterait plus que cela ne rapporte. Tests : `core/tests/test_purge_du_cache.py`, qui monte la **vraie** table — le cache en mémoire des tests purge autrement |
| 70 | Attendre la base, oui ; attendre sans fin, non | **`DELAIS_POSTGRES`** (`config.settings`) pose quatre bornes sur la base : `connect_timeout` 3 s et des sondes TCP côté client, `statement_timeout` 15 s, `lock_timeout` 10 s et `idle_in_transaction_session_timeout` 5 min côté serveur. Les trois réglages Postgres valaient **zéro — l'infini** — et aucun délai n'était posé côté client : c'est la panne du stockage (décision 60) à l'identique, sur la base cette fois. L'audit de résilience l'a mesuré — une base qui accepte la connexion sans jamais répondre faisait **pendre toute l'API au-delà de quatre-vingt-dix secondes**, `/api/health/` compris. Après correction : **503 en 3,0 s** ; une requête trop longue rend 503 en 0,35 s ; un verrou tenu par un voisin est refusé à 10,05 s au lieu d'être attendu sans fin — toutes avec `Retry-After` (décision 62). Les deux familles sont nécessaires : un délai côté serveur ne peut rien quand c'est le serveur qui manque. `entrypoint.sh` **lève le délai d'instruction pour les migrations** — un `CREATE INDEX` sur une grande table le dépasse légitimement — mais garde `lock_timeout` : une migration qui n'obtient pas son verrou doit échouer bruyamment plutôt que bloquer la livraison en silence. **Limite connue, non couverte** : un processus Postgres vivant au niveau TCP mais qui ne répond plus (figé, ou machine dont le noyau acquitte encore) — mesuré, la requête pend toujours au-delà de 95 s, et aucun réglage de connexion ne peut y répondre. `restart: unless-stopped` ne relève pas un conteneur déclaré malsain, seulement un conteneur sorti : le rétablissement reste manuel. Tests : `config/tests/test_delais_base.py` |
| 71 | Les pannes combinées ne s'amplifient pas | Constat, sans correctif : la Phase 3 de l'audit a superposé les pannes deux à deux et trois à trois, et **aucune combinaison n'a produit pire que sa cause dominante**. Pic de trafic (16 clients) plus latence de base : 50 → 27 → 6,9 → 1,4 req/s à 0, 5, 25 et 100 ms, **zéro erreur à chaque palier** — la dégradation est régulière, sans falaise, mais **silencieuse** : à 100 ms, le P99 atteint 13,6 s et rien ne le dit (c'est ce que la décision 70 borne désormais). Quatre cœurs saturés **ne changent rien** (50,8 req/s contre 49,6 au repos) : depuis la décision 67, l'écran des dépenses attend le réseau, il ne calcule plus — ce qui corrige la capacité annoncée plus tôt dans l'audit, « ~31 req/s, limité par le processeur ». CPU saturé plus latence donne exactement la latence seule (6,7 contre 6,9 req/s). Enfin, un worker abattu au SIGKILL sous latence, courrier mort et ordonnanceur arrêté perd **5 requêtes sur 99** — celles en vol sur ce worker, pas une de plus —, le worker renaît et l'API répond en 44 ms. Rien à corriger ; la propriété était à établir |
| 72 | L'index suit le tri, et il n'y en a qu'un | **`depense_tri_liste`** (`-date, -created_at, -id`) remplace l'index sur `date` seul. La liste des dépenses se trie exactement ainsi : Postgres lit désormais les vingt-cinq lignes d'une page **dans l'index, sans rien trier** — cinq pages lues au lieu de 6 009 lignes parcourues puis triées. Mesuré, à volume croissant sur la même table : **0,95 ms → 0,015 ms** à 6 000 lignes, **3,37 → 0,016** à 60 000, **15,59 → 0,018** à 600 000. Le coût sans index suit la table ; avec index il est plat. Prix à l'écriture : **+11 %, soit 2 µs par ligne**, et 256 ko pour une table de 2 Mo. Ce que l'index n'achète **pas** : du débit aujourd'hui — sous charge à 6 009 lignes, 63,9 contre 62,7 req/s, dans le bruit, la requête SQL ne pesant que 3 ms sur 250. Il achète la tenue dans dix ans. Un second index candidat (`country_id` en tête) a été mesuré puis **écarté** : le planificateur ne le choisissait jamais, et il se serait pourtant payé à chaque écriture ; pour les filtres sélectifs, Postgres bascule seul sur `depense_pays_statut_date`. Aucun index ajouté ailleurs : `authtoken_token`, `auth_user`, `core_country` et `core_team` tiennent sur **une seule page** — leur parcours complet coûte 0,024 ms et un index y serait plus lent. Tests : `expenses/tests/test_queries.py` (`IndexDeTriTests`), qui garde non pas l'existence de l'index mais **qu'il corresponde encore à `ordering`** : changer le tri sans changer l'index ne casse rien de visible, la liste redevient simplement lente, en silence |
| 73 | Le cache sort de la base, avec un filet | **Redis est le cache principal** (`REDIS_URL`, `core.cache.CacheAvecSecours`) ; sans cette variable, la base de données reprend le rôle et la pile démarre comme avant. Motif mesuré : la limitation de débit relisait et réécrivait l'historique de chaque compte à chaque requête — **1 478 octets de journal d'écriture par `GET`** et **quatre requêtes sur `django_cache` par appel**, désormais **zéro** des deux. Cela referme au passage une exception non documentée à la règle « une requête `GET` n'écrit rien ». Le débit, lui, ne bouge pas — 62,0 contre 62,6 req/s : Redis achète l'arrêt des écritures et la sûreté des compteurs, **pas de la vitesse**. Éviction par clé la moins récemment utilisée, là où `DatabaseCache` purgeait par ordre alphabétique et emportait les compteurs anti-bourrage en premier (décision 69). **Le filet n'est pas optionnel** : le client de Redis lève quand le serveur ne répond pas, et un cache sans repli ferait de chaque requête une 500 — la plateforme serait *moins* sûre qu'avant. Le repli sur `django_cache` est mesuré : écriture et lecture passent, une seule ligne de journal par minute, le service continue. Ce que le repli ne rattrape pas, et c'est assumé : les compteurs de débit repartent de zéro — un quota rouvert vaut mieux qu'une plateforme fermée, et le verrou qui rend le comptage exact (décision 68) vit dans PostgreSQL, où que soit le compteur. Le serveur **et l'ordonnanceur** pointent sur le même cache : la configuration du circuit y est gardée sans expiration et c'est le serveur qui l'invalide ; deux caches distincts laisseraient l'ordonnanceur notifier selon une politique périmée, indéfiniment. Délais bornés côté client (1 s), comme pour le stockage (déc. 60) et la base (déc. 70). Tests : `core/tests/test_cache_de_secours.py` |

### Décisions contraires au cadrage initial, assumées

Le cadrage d'origine n'est plus dans le dépôt : il portait le nom d'un autre
projet et ne décrivait pas l'application telle qu'elle est. Ce qu'il
demandait et que l'on a choisi de ne pas faire reste consigné ici, pour que
la question ne soit pas rouverte par oubli.

| # | Ce que demandait le cadrage | Choix retenu et raison |
|---|---|---|
| C1 | Validation par délégation au responsable pays | **Pas de délégation.** Le manager déclare, le DM contrôle, le DF constate : un manager qui justifierait les dépenses de son pays viderait l'application de son objet. Les capacités de contrôle (`expenses.validate`, `expenses.review`, `expenses.close`, `proofs.review`, `dossiers.reopen`) sont verrouillées pour le rôle pays : la matrice configurable ne peut pas les lui ouvrir. |
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
