# Plateforme de contrôle budgétaire

Suivi budgétaire centralisé : référentiel pays et organisations, comptes et
périmètres, enveloppes annuelles, réallocations et historique des changements.

## Architecture

| Service   | Techno                                        | Port  |
|-----------|-----------------------------------------------|-------|
| Backend   | Django 5 + Django REST Framework + PostgreSQL | 8000  |
| Frontend  | React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui | 5173 |
| Base      | PostgreSQL 16                                 | 5433  |

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
docker compose up --build
```

- Frontend : http://localhost:5173
- API : http://localhost:8000/api/
- Admin Django : http://localhost:8000/admin/

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
| `admin` | tous pays | référentiels, comptes et rôles |
| `doo` | tous pays | attribuer les budgets, arbitrer les réallocations |
| `controller` | tous pays | contrôler et auditer, en lecture |
| `auditor` | tous pays | lecture seule |
| `country_manager` | ses pays | gérer les sous-entités de son pays |
| `owner` | ses pays | saisir ses dépenses (lot 2) |

Le périmètre est porté par le profil : un rôle du siège sans pays explicite
couvre tous les pays, tandis qu'un rôle pays **sans** périmètre ne voit rien —
l'absence de périmètre ne vaut jamais autorisation générale. Un pays hors
périmètre répond 404, sans révéler son existence.

## Démarrage manuel (dev sans conteneur frontend)

Backend (PostgreSQL requis, ou `docker compose up -d db backend`) :

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

Frontend (Node 20+) :

```bash
cd frontend
npm install
npm run dev
```

Vite proxy les appels `/api` vers `http://localhost:8000`.

## API REST

Toutes les routes exigent un jeton `Authorization: Token <token>`.

> **Pas de suppression.** Le retrait d'une entité se fait par désactivation
> (`is_active`), jamais par `DELETE` : supprimer un pays effacerait en cascade
> ses équipes, centres de coûts et projets. Les routes `DELETE` répondent 405.
> L'obtention du jeton est limitée à 10 tentatives par minute et par adresse IP.

```
POST   /api/token-auth/                  # obtention du jeton (username/password)
GET    /api/countries/                   # liste paginée (filtres: is_active, search, ordering)
POST   /api/countries/                   # création
GET    /api/countries/{id}/              # détail + entités liées
PATCH  /api/countries/{id}/              # modification / activation / désactivation
GET    /api/history/?country={id}        # historique des changements
GET/POST/PATCH /api/managers/            # managers
GET/POST/PATCH /api/teams/               # équipes
GET/POST/PATCH /api/cost-centers/        # centres de coûts
GET/POST/PATCH /api/projects/            # projets
GET/POST/PATCH /api/expense-titles/      # intitulés de dépenses
GET/POST/PATCH /api/marketing-categories/# catégories marketing

GET    /api/me/                          # rôle, périmètre et droits du compte
POST   /api/me/password/                 # changement de mot de passe
GET/POST/PATCH /api/users/               # comptes (siège uniquement)

GET/POST/PATCH /api/budgets/             # enveloppes annuelles et sous-enveloppes
GET    /api/budgets/summary/             # consolidation par pays, total en FCFA
GET/POST /api/reallocations/             # demandes de transfert entre enveloppes
POST   /api/reallocations/{id}/approve/  # exécute le transfert
POST   /api/reallocations/{id}/reject/   # motif obligatoire
GET/POST/PATCH /api/exchange-rates/      # taux de conversion vers le FCFA

GET/POST/PATCH /api/dossiers/            # dossiers de justification (N°ORDRE)
POST   /api/dossiers/{id}/submit|review|approve|reject|close/
GET/POST/PATCH /api/expenses/            # lignes de dépenses (mêmes transitions)
GET/POST /api/proofs/                    # justificatifs (dépôt multipart)
GET    /api/proofs/{id}/download/        # téléchargement contrôlé et tracé
POST   /api/proofs/{id}/review/          # contrôle documentaire
GET/POST/PATCH /api/beneficiaries/       # prospects et bénéficiaires
GET    /api/audit/                       # journal d'audit

GET    /api/dashboard/                   # consolidation, charge et alertes
GET    /api/dashboard/breakdown/         # répartition équipe/manager/projet/mois
GET    /api/exports/expenses.xlsx        # export au format du fichier historique
GET    /api/exports/reconciliation.xlsx  # rapprochement dépenses / justifiés
GET    /api/exports/report.pdf           # rapport de synthèse
GET    /api/notifications/               # centre de notifications
```

Les listes acceptent `?country__country_ref=TG-02` pour cibler un pays par
son identifiant fonctionnel, ainsi que `?year=`, `?status=` et `?search=`.

Toutes les listes sont filtrées par le périmètre du compte.

## Budgets

Une enveloppe est annuelle et rattachée à un pays ; renseigner un projet en
fait une **sous-enveloppe**, c'est-à-dire un découpage de l'enveloppe du pays
(la consolidation ne l'additionne donc pas, sous peine de compter deux fois le
même argent).

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

## Tests

```bash
docker compose run --rm --entrypoint python backend manage.py test
```

## Variables d'environnement

| Variable | Défaut | Rôle |
|----------|--------|------|
| `DJANGO_DEBUG` | `0` | `1` active le mode debug (dev uniquement) |
| `DJANGO_SECRET_KEY` | — | **obligatoire** hors mode debug |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | hôtes autorisés, séparés par des virgules |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | origines autorisées |
| `DJANGO_SECURE_SSL_REDIRECT` | `1` | redirection HTTPS hors mode debug |
| `DJANGO_CREATE_SUPERUSER` | `0` | `1` crée un compte d'amorçage, avec `DJANGO_SUPERUSER_PASSWORD` |
| `POSTGRES_*` | voir `docker-compose.yml` | connexion à la base |
| `AWS_S3_ENDPOINT_URL` | — | active le stockage objet ; disque local si vide |
| `MAX_PROOF_SIZE` | `20971520` | taille maximale d'un justificatif (octets) |
| `ALERT_THRESHOLDS` | `80,90,100` | seuils de consommation déclenchant une alerte |
| `UNUSUAL_EXPENSE_FACTOR` | `5` | multiple de la moyenne au-delà duquel une dépense est signalée |
| `EMAIL_HOST` | — | serveur SMTP ; sans lui, les e-mails vont dans les logs |
| `APP_BASE_URL` | `http://localhost:5173` | base des liens dans les e-mails |
| `DJANGO_TIME_ZONE` | `UTC` | fuseau de référence du serveur |

## Capture d'écran (revue visuelle)

Un script Playwright parcourt l'application et capture les écrans principaux,
depuis un compte du siège **et** depuis un compte pays, afin de vérifier le
cloisonnement. Les identifiants viennent de l'environnement, jamais du code :

```bash
cd frontend
npx playwright install chromium
SHOT_HQ_USER=… SHOT_HQ_PASSWORD=… \
SHOT_COUNTRY_USER=… SHOT_COUNTRY_PASSWORD=… \
npx tsx scripts/screenshot.ts
# → /tmp/shot_countries_hq.png, shot_budgets_pays.png, shot_users.png, …
```

Le script échoue si la console du navigateur a produit la moindre erreur.
## Workflow et dossiers

Le **N°ORDRE** devient un dossier de justification : il regroupe les lignes de
dépenses d'une opération et les preuves qui les appuient. Dossier et lignes
suivent chacun leur circuit :

```
brouillon → soumis → en contrôle → validé / refusé → clôturé
```

Le statut n'est jamais modifiable par écriture de champ : seules les
transitions déclarées le font évoluer, et chacune est journalisée. Un rejet
exige un motif, une dépense validée ne se corrige plus en place, et un dossier
ne peut être validé sans justificatif.

Une dépense soumise **engage** son enveloppe ; validée, elle la **consomme**.
Le disponible retranche les deux. La politique de dépassement de l'enveloppe
décide de la suite : bloquer, alerter, ou réserver la validation à la
direction des opérations — le manager pouvant dans tous les cas formuler la
demande.

## Justificatifs

Chaque pièce porte son empreinte SHA-256, sa taille et sa version. Redéposer
un fichier déjà présent sur le même dossier est refusé, sauf remplacement
explicite, qui archive la version précédente. Les formats acceptés sont
limités par liste blanche. Le téléchargement passe par une vue authentifiée
plutôt que par une URL signée : le périmètre est vérifié à chaque accès et
chaque téléchargement laisse une trace.

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
