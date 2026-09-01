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
```

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