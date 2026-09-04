# Plateforme de contrôle budgétaire

Suivi budgétaire centralisé et traçable : référentiel pays et organisations,
comptes et périmètres, enveloppes annuelles, dossiers de justification,
dépenses, pièces justificatives, workflow de validation, tableaux de bord
temps réel, alertes et exports.

## Architecture

| Service   | Techno                                        | Port (127.0.0.1) |
|-----------|-----------------------------------------------|-------|
| Backend   | Django 5.2 + Django REST Framework + gunicorn | 8000  |
| Frontend  | React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui | 5173  |
| Base      | PostgreSQL 16                                 | 5433  |
| Stockage  | MinIO (justificatifs, API S3)                 | 9000, console 9001 |
| Ordonnanceur | `manage.py run_scheduler` (alertes, rapports) | —  |

En développement, les ports ne sont ouverts que sur la boucle locale.

Applications Django :

| App        | Rôle |
|------------|------|
| `core`     | Référentiel (pays, managers, équipes, centres de coûts, projets, intitulés, catégories) et historique |
| `accounts` | Profils, rôles, périmètres pays, cloisonnement |
| `budget`   | Enveloppes annuelles, sous-enveloppes, réallocations, taux de change |
| `expenses` | Dossiers (N°ORDRE), dépenses, justificatifs, workflow, audit |
| `notifications` | Notifications in-app et e-mail |
| `reporting` | Tableaux de bord, alertes, exports Excel et PDF |

## Démarrage (Docker)

```bash
docker compose up -d          # db, minio, backend, scheduler, frontend
```

- Frontend : http://localhost:5173
- API : http://localhost:8000/api/
- Admin Django : http://localhost:8000/admin/
- `GET /api/health/` : état du serveur et de la base, sans authentification ;
  c'est ce que lisent les contrôles de santé Docker et la livraison continue.

### Création des comptes

Aucun compte n'est créé automatiquement et **aucun mot de passe ne figure dans
le dépôt**. Les comptes sont décrits dans un fichier local ignoré par git :

```bash
cd backend
cp seed_users.example.json seed_users.local.json   # puis renseignez-le
docker compose exec backend python manage.py seed_users --dry-run
docker compose exec backend python manage.py seed_users
```

La commande est idempotente : elle crée ou met à jour pays et comptes, et
adopte un pays préexistant plutôt que d'échouer sur son nom.

### Rôles et périmètres

| Rôle | Périmètre | Peut |
|------|-----------|------|
| `super_admin` | tous pays | tout, y compris le back-office Django |
| `admin` | tous pays | référentiels, comptes, rôles, **et justification** |
| `doo` | tous pays | attribuer les budgets, arbitrer, **justifier** |
| `controller` | tous pays | contrôler les pièces, **justifier ou non** |
| `auditor` | tous pays | lecture seule |
| `country_manager` | ses pays | gérer son pays, saisir et **soumettre** |
| `owner` | ses pays | saisir ses dépenses et déposer les justificatifs |

**Le pays déclare, le siège constate.** Un responsable pays ne peut ni
justifier, ni déclarer non justifiée, ni prendre en contrôle, ni clôturer une
dépense — pas même les siennes. Autrement, il pourrait décaisser puis se donner
quitus, ce qui viderait l'application de sa raison d'être.

La séparation vaut aussi **à l'intérieur du siège** : celui qui a saisi une
dépense ne peut pas la justifier lui-même. Il faut deux personnes.

Le périmètre est porté par le profil : un rôle du siège sans pays explicite
couvre tous les pays, tandis qu'un rôle pays **sans** périmètre ne voit rien —
l'absence de périmètre ne vaut jamais autorisation générale. Un pays hors
périmètre répond 404, sans révéler son existence.

## Démarrage manuel (sans conteneur backend ni frontend)

Backend, avec la base du `docker compose` (`docker compose up -d db minio`),
joignable sur `127.0.0.1:5433` :

```bash
cd backend
pip install -r requirements.txt
export DJANGO_DEBUG=1 POSTGRES_HOST=localhost POSTGRES_PORT=5433
python manage.py migrate
python manage.py seed_users --file seed_users.local.json
python manage.py runserver 0.0.0.0:8000
```

Frontend (Node 24, la version de l'image de production) :

```bash
cd frontend
npm ci
npm run dev
```

Vite proxy les appels `/api` vers `http://localhost:8000`.

## API REST

Toutes les routes exigent un jeton `Authorization: Token <token>`.

> **Pas de suppression.** Le retrait d'une entité se fait par désactivation
> (`is_active`), jamais par `DELETE` : supprimer un pays effacerait en cascade
> ses équipes, centres de coûts et projets. Les routes `DELETE` répondent 405 —
> sauf pour un dossier ou une dépense **en brouillon**, que son auteur peut
> retirer. L'obtention du jeton est limitée à 10 tentatives par minute et par
> adresse IP ; un jeton expire après `TOKEN_MAX_AGE_DAYS`.

```
GET    /api/health/                      # état du serveur et de la base (sans jeton)
POST   /api/token-auth/                  # obtention du jeton (username/password)
POST   /api/logout/                      # révocation du jeton
GET    /api/me/                          # rôle, périmètre et droits du compte
POST   /api/me/password/                 # changement de mot de passe
GET    /api/permissions/                 # matrice rôle × action, telle que le serveur l'applique
GET/PATCH /api/configuration/            # réglages de la plateforme (siège)
GET/PATCH /api/workflow-configuration/   # politique du circuit : étape de contrôle, seuils, dépassement
GET/POST/PATCH /api/users/               # comptes (siège uniquement)

GET    /api/countries/                   # liste paginée (filtres: is_active, search, ordering)
GET    /api/countries/disponibles/       # codes ISO africains pas encore créés
POST   /api/countries/                   # création (code africain obligatoire)
GET    /api/countries/{id}/              # détail + entités liées
PATCH  /api/countries/{id}/              # modification / activation / désactivation
GET    /api/history/?country={id}        # historique des changements
GET/POST/PATCH /api/managers/            # managers
GET/POST/PATCH /api/teams/               # équipes
GET/POST/PATCH /api/cost-centers/        # centres de coûts
GET/POST/PATCH /api/projects/            # projets
GET/POST/PATCH /api/expense-titles/      # intitulés de dépenses
GET/POST/PATCH /api/marketing-categories/# catégories marketing

GET/POST/PATCH /api/budgets/             # enveloppes annuelles et sous-enveloppes (?year=)
GET    /api/budgets/summary/             # consolidation par pays, total en FCFA
GET/POST /api/reallocations/             # demandes de transfert entre enveloppes
POST   /api/reallocations/{id}/approve/  # exécute le transfert
POST   /api/reallocations/{id}/reject/   # motif obligatoire
GET/POST/PATCH /api/exchange-rates/      # taux de conversion vers le FCFA

GET/POST/PATCH /api/dossiers/            # dossiers de justification (N°ORDRE)
DELETE /api/dossiers/{id}/               # brouillon seul, par son auteur
POST   /api/dossiers/{id}/submit/        # soumet le dossier et ses lignes (avertit s'il n'a pas de pièce)
POST   /api/dossiers/{id}/review|justify|reject|close/
GET/POST/PATCH /api/expenses/            # lignes de dépenses
DELETE /api/expenses/{id}/               # brouillon seul, par son auteur
POST   /api/expenses/{id}/review|justify|reject|close/
GET    /api/expenses/register/           # registre : chaque dépense et ses preuves
GET/POST /api/proofs/                    # justificatifs (dépôt multipart)
GET    /api/proofs/{id}/download/        # téléchargement contrôlé et tracé
POST   /api/proofs/{id}/review/          # contrôle documentaire
GET/POST/PATCH /api/beneficiaries/       # prospects et bénéficiaires, par pays
GET    /api/audit/                       # journal d'audit

GET    /api/dashboard/                   # consolidation, charge et alertes
GET    /api/dashboard/breakdown/         # répartition équipe/manager/projet/mois
GET    /api/exports/expenses.xlsx        # export au format du fichier historique
GET    /api/exports/reconciliation.xlsx  # rapprochement dépenses / justifiés
GET    /api/exports/report.pdf           # rapport de synthèse
POST   /api/imports/expenses.xlsx        # import au format de l'export (rôles de saisie)
GET    /api/notifications/               # centre de notifications
GET    /api/notifications/unread_count/
POST   /api/notifications/{id}/read/ · /api/notifications/read-all/
```

`review`, `justify`, `reject` et `close` sont les transitions du circuit de
justification (voir plus bas) ; `reject` exige un motif.

Les listes acceptent `?country__country_ref=TG-02` pour cibler un pays par
son identifiant fonctionnel, ainsi que `?status=` et `?search=` ; `?year=`
vaut pour les enveloppes. Le registre accepte en plus `?date__gte=` et
`?date__lte=` pour une période. Toutes les listes sont paginées : `?page=` et
`?page_size=` (plafonné à 200).

Toutes les listes sont filtrées par le périmètre du compte. Les exports et le
téléchargement d'une pièce sont les seules requêtes `GET` qui écrivent :
elles laissent une entrée dans le journal d'audit, parce qu'une donnée qui
sort du système doit laisser une trace.

## Budgets

Une enveloppe est annuelle et rattachée à un pays. Elle se décline en
**sous-enveloppes** selon **une** dimension à la fois — un projet, une équipe
ou un manager. En autoriser plusieurs rendrait l'imputation d'une dépense
ambiguë ; la contrainte est posée en base autant que dans l'API.

Une sous-enveloppe découpe l'enveloppe du pays : la consolidation ne
l'additionne donc pas, sous peine de compter deux fois le même argent. Une
dépense s'impute sur la plus précise qui la concerne — le projet l'emporte sur
l'équipe, qui l'emporte sur le manager — et à défaut sur l'enveloppe du pays.

Tout mouvement budgétaire est journalisé : création, modification de montant,
réallocation et taux de change apparaissent dans `/api/history/`, avec leur
auteur et les champs touchés.

Consommation, écart et solde disponible sont **calculés côté serveur** et
jamais reconstitués dans l'interface. Les montants sont stockés dans la devise
du pays ; la consolidation au siège se fait en FCFA au taux en vigueur à la
date de l'opération. Une devise sans taux connu est **exclue du total et
signalée**, plutôt que d'y être absorbée silencieusement.

## Historique des changements

Les événements suivants sont auto-journalisés dans `ChangeLog` :

- **Création** d'un pays / manager / équipe / centre de coûts / etc.
- **Mise à jour** d'une entité.
- **Changement de rattachement** : une sous-entité (équipe, centre de coûts,
  projet…) rattachée à un autre pays.
- **Désactivation / réactivation** d'un pays.
- **Suppression** effectuée hors API (admin Django, shell), y compris en
  cascade.

Chaque entrée conserve `label`, `performed_by` (utilisateur authentifié),
`from_value` / `to_value`, `changed_fields` et `created_at`. Une modification
qui combine plusieurs natures d'événement (par exemple un changement de
rattachement *et* un renommage) produit une entrée par événement.

## Tâches planifiées

Elles tournent dans le service `scheduler`, démarré avec le reste de la pile.
Elles vivaient auparavant dans ce fichier sous forme de lignes de crontab à
poser sur l'hôte : documentées, donc jamais posées — et une alerte qui n'est
pas planifiée n'avertit personne. Un dépassement survenu un dimanche attendait
que quelqu'un ouvre une page.

Le service est distinct du backend : lancées dans celui-ci, les tâches
s'exécuteraient une fois par worker gunicorn (`GUNICORN_WORKERS`), soit autant
de notifications pour une seule alerte.

```bash
docker compose logs -f scheduler                    # ce qui est planifié
docker compose exec scheduler python manage.py run_scheduler --list
docker compose exec scheduler python manage.py run_scheduler --once  # tout, tout de suite
```

| Tâche | Cadence par défaut | Variable |
|---|---|---|
| Notification des alertes | toutes les heures | `SCHEDULE_ALERTS` |
| Rapport de rapprochement hebdomadaire | lundi 7 h | `SCHEDULE_WEEKLY_REPORT` |
| Rapport de rapprochement mensuel | le 1er à 7 h | `SCHEDULE_MONTHLY_REPORT` |

Les cadences se surchargent par l'environnement, en syntaxe cron, sans
reconstruire l'image. Une tâche qui échoue — SMTP injoignable, base
momentanément indisponible — est journalisée et n'emporte pas les suivantes.

Les deux commandes restent lançables à la main, avec `--dry-run` :

```bash
docker compose exec backend python manage.py notify_alerts --dry-run
docker compose exec backend python manage.py send_periodic_report \
    --period=weekly --dry-run
```

Les alertes sont *calculées* à chaque lecture du tableau de bord ; seule leur
*notification* passe par la commande. Séparer les deux évite qu'une requête de
lecture écrive en base.

## Tests

```bash
docker compose run --rm --entrypoint python backend manage.py test
cd frontend && npx tsc -b && npm run lint && npm run test
```

Ce sont les commandes de `CLAUDE.md` et de la CI. **Deux suites backend ne
tournent pas en parallèle sur la même base** : Django crée `test_<POSTGRES_DB>`
et la détruit à la fin ; la seconde suite détruirait celle de la première.
Pour travailler à plusieurs, donnez à chacune sa base :
`docker compose run --rm -e POSTGRES_DB=justi_<nom> --entrypoint python backend manage.py test`.

## Intégration et livraison continues

L'intégration continue (`.github/workflows/ci.yml`) tourne sur chaque PR et
au sein de la livraison continue, en cinq travaux indépendants :

| Travail | Ce qu'il vérifie |
|---|---|
| Backend | migrations à jour, `check --deploy`, suite Django hors mode debug |
| Frontend | types, lint, tests unitaires, build |
| Images Docker | les deux images se construisent |
| Parcours complet | la pile livrable (backend en production, frontend nginx) démarre, des comptes jetables s'y connectent, les trois scripts de capture de `DESIGN.md` (parcours, connexion, thème sombre) passent sans erreur de console ; les captures sont publiées en artefact |
| Dépendances | `pip-audit --strict` et `npm audit --audit-level=high`, **bloquants** |

La livraison continue (`.github/workflows/cd.yml`) appelle la CI, puis :

```
main ──────▶ CI ──▶ images ghcr.io ──▶ staging      (automatique)
tag v1.2.3 ▶ CI ──▶ images ghcr.io ──▶ production   (approbation requise, tags v* seulement)
```

Les images sont étiquetées par le SHA du commit — jamais `latest` — ; c'est
cette étiquette que le serveur reçoit, si bien que revenir en arrière consiste
à redéployer la précédente, ce que `deploy.sh` fait de lui-même si la
nouvelle pile ne devient pas saine. Le déploiement n'est déclaré réussi que
lorsque tous les conteneurs passent leur contrôle de santé et que
`/api/health/` répond depuis l'extérieur. La préparation du serveur, les
secrets attendus, la coupure pendant les migrations et le retour arrière
sont décrits dans [`deploy/README.md`](deploy/README.md).

Les mises à jour de dépendances arrivent en PR via Dependabot
(`.github/dependabot.yml`), donc passent par la CI.

## Variables d'environnement

Le modèle complet pour un serveur est `deploy/.env.example`.

| Variable | Défaut | Rôle |
|----------|--------|------|
| `DJANGO_DEBUG` | `0` | `1` active le mode debug (dev uniquement) |
| `DJANGO_SECRET_KEY` | — | **obligatoire** hors mode debug |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | hôtes autorisés, séparés par des virgules |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | origines autorisées |
| `DJANGO_SECURE_SSL_REDIRECT` | `1` | redirection HTTPS hors mode debug ; `/api/health/` en est exempté |
| `DJANGO_HSTS_PRELOAD` | `1` | inscription HSTS sur la liste de préchargement des navigateurs (hors debug) |
| `DJANGO_NUM_PROXIES` | — | nombre de proxys de confiance devant Django (2 en production : Caddy puis nginx ; 1 en CI) pour lire la vraie adresse du client |
| `TOKEN_MAX_AGE_DAYS` | `30` | durée de vie d'un jeton d'API |
| `DJANGO_TIME_ZONE` | `UTC` | fuseau de référence du serveur |
| `DJANGO_CREATE_SUPERUSER` | `0` | `1` crée un compte d'amorçage au démarrage, profil `super_admin` et mot de passe provisoire |
| `DJANGO_SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` | `admin` / — / — | identité de ce compte ; sans mot de passe, rien n'est créé |
| `POSTGRES_HOST` / `_PORT` / `_DB` / `_USER` / `_PASSWORD` | `db` / `5432` / `justi_innov` / `justi` / `justi` | connexion à la base |
| `AWS_S3_ENDPOINT_URL` | — | active le stockage objet (MinIO) ; disque local si vide |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_STORAGE_BUCKET_NAME` | — / — / `justificatifs` | accès au stockage objet |
| `MAX_PROOF_SIZE` | `20971520` | taille maximale d'un justificatif (octets) |
| `ALERT_THRESHOLDS` | `80,90,100` | seuils de consommation déclenchant une alerte (valeurs initiales de la configuration du workflow) |
| `UNUSUAL_EXPENSE_FACTOR` | `5` | multiple de la moyenne au-delà duquel une dépense est signalée (idem) |
| `UNJUSTIFIED_ALERT_DAYS` | `0` | jours sans pièce après soumission avant alerte ; `0` désactive (idem) |
| `WARN_WITHOUT_PROOF_SUBMISSION` | `1` | avertir à la soumission d'un dossier sans pièce (idem) |
| `EMAIL_HOST` | — | serveur SMTP ; sans lui, les e-mails vont dans les logs |
| `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` / `EMAIL_USE_TLS` | `587` / — / — / `1` | paramètres SMTP |
| `DEFAULT_FROM_EMAIL` | `controle-budgetaire@justi-innov.local` | expéditeur des e-mails |
| `APP_BASE_URL` | `http://localhost:5173` | base des liens dans les e-mails |
| `SCHEDULE_ALERTS` / `SCHEDULE_WEEKLY_REPORT` / `SCHEDULE_MONTHLY_REPORT` | `0 * * * *` / `0 7 * * 1` / `0 7 1 * *` | cadences de l'ordonnanceur, syntaxe cron |
| `GUNICORN_WORKERS` / `GUNICORN_THREADS` / `GUNICORN_TIMEOUT` | `2` / `4` / `120` | processus, fils par processus et délai (s) du serveur d'application |

## Capture d'écran (revue visuelle)

Trois scripts Playwright, décrits dans `DESIGN.md`, parcourent l'application
et capturent les écrans : le parcours complet depuis un compte du siège
**et** un compte pays (cloisonnement), l'écran de connexion sur grand écran et
mobile, et les écrans principaux dans les deux thèmes. Les identifiants
viennent de l'environnement, jamais du code :

```bash
cd frontend
npx playwright install chromium
SHOT_HQ_USER=… SHOT_HQ_PASSWORD=… \
SHOT_COUNTRY_USER=… SHOT_COUNTRY_PASSWORD=… \
npx tsx scripts/screenshot.ts     # → /tmp/shot_countries_hq.png, shot_budgets_pays.png, …
npx tsx scripts/shot-login.ts
npx tsx scripts/shot-theme.mts
```

Chaque script échoue si la console du navigateur a produit la moindre erreur.
La CI les rejoue sur la pile livrable.

## Circuit de justification

Le but de l'application n'est pas d'autoriser des dépenses : c'est de savoir
**ce que le pays a dépensé, quand, où, au profit de qui — et où est la
preuve**. Le contrôleur ne valide pas un achat déjà fait ; il constate qu'une
pièce le couvre. D'où « justifié » plutôt que « validé ».

Le **N°ORDRE** est le dossier de justification : il regroupe les lignes de
dépenses d'une opération et les preuves qui les appuient. Dossier et lignes
suivent chacun leur circuit :

```
brouillon → soumis → en contrôle → justifié / non justifié → clôturé
```

Côté pays, déclarer une dépense tient en **une action** : remplir les lignes,
joindre le justificatif, soumettre le dossier — ses lignes partent avec lui.
Le reste est calculé par le système et relève du siège.

Un dossier ne se soumet pas vide : les lignes viennent d'abord. En revanche,
l'absence de justificatif **n'empêche pas** la déclaration, elle l'accompagne
d'un avertissement. Bloquer signifierait qu'une dépense sans reçu ne serait
jamais déclarée : l'argent sortirait sans laisser de trace, ce qui est pire que
l'écart.

Deux principes gouvernent ce circuit :

**Une fois soumise, une dépense est irréversible.** Elle ne revient jamais au
brouillon, ne se modifie plus, ne se supprime pas. L'argent est sorti :
l'effacer reviendrait à en perdre la trace. Seul un brouillon — jamais
soumis, donc sans valeur probante — peut être retiré, par son auteur, et sa
suppression est elle-même journalisée.

**Une dépense non justifiée pèse malgré tout sur l'enveloppe.** L'absence de
preuve ne fait pas revenir l'argent. Elle se lit dans l'écart entre le montant
dépensé et le montant justifié — le chiffre que l'application existe pour
faire diminuer. Une preuve déposée après coup reste le seul chemin de
rattrapage : le contrôleur peut alors marquer la dépense justifiée.

Le statut n'est jamais modifiable par écriture de champ : seules les
transitions déclarées le font évoluer, et chacune est journalisée. Un constat
de non-justification exige un motif, et un dossier ne peut être justifié sans
pièce.

Une dépense soumise **engage** son enveloppe ; contrôlée, elle la **consomme**
— qu'elle soit justifiée ou non. Le disponible retranche les deux. La
politique de dépassement décide de la suite : bloquer, alerter, ou réserver la
justification à la direction des opérations — le manager pouvant dans tous les
cas déclarer la dépense.

## Justificatifs

Chaque pièce porte son empreinte SHA-256, sa taille et sa version. Redéposer
un fichier déjà présent sur le même dossier est refusé, sauf remplacement
explicite, qui archive la version précédente. Les formats acceptés sont
limités par liste blanche. Le téléchargement passe par une vue authentifiée
plutôt que par une URL signée : le périmètre est vérifié à chaque accès et
chaque téléchargement laisse une trace.

## Heure locale

Les dates sont stockées en UTC, mais une dépense se lit à l'heure du pays où
elle a eu lieu : le registre et le détail d'un dossier affichent l'heure locale
et nomment le fuseau (§6). Sans cela, un contrôleur au siège verrait l'heure de
son propre fuseau, ce qui fausse le « quand » d'une dépense.

## Registre de justification

Le journal d'audit dit *qui a fait quoi*. Le registre, lui, répond à la
question qui motive l'application : **où est passé l'argent ?** Chaque dépense
y figure avec sa date et son heure, son pays, son lieu, son équipe, son
propriétaire, son bénéficiaire, son projet, son mode de paiement, le montant
dépensé, le montant justifié, l'écart — et les pièces qui l'attestent, avec la
mention de celles jugées incomplètes. Une dépense sans preuve est signalée
comme telle.

## Pilotage, alertes et exports

Le tableau de bord consolide les enveloppes en FCFA, expose la charge de
contrôle et calcule les alertes : seuils de consommation, dépassements,
dossiers engagés sans preuve, justificatifs incomplets et dépenses
inhabituelles. Une dépense est jugée inhabituelle par rapport aux **autres**
dépenses de son pays — s'inclure dans sa propre référence l'empêcherait de
s'en détacher.

Les alertes budgétaires deviennent des notifications persistantes, in-app et
par e-mail, avec une clé d'unicité qui évite de signaler deux fois le même
franchissement.
