# Pays & Organisations — Module 5.1

Gestion des pays et organisations : pays (devise, fuseau horaire, managers),
équipes, centres de coûts, projets, intitulés de dépenses, catégories
marketing, et historique des changements de rattachement.

## Architecture

| Service   | Techno                                        | Port  |
|-----------|-----------------------------------------------|-------|
| Backend   | Django 5 + Django REST Framework + PostgreSQL | 8000  |
| Frontend  | React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui | 5173 |
| Base      | PostgreSQL 16                                 | 5433  |

## Démarrage (Docker)

```bash
docker compose up --build
```

Le service backend applique les migrations et crée le super-utilisateur
`admin` / `admin123` au premier démarrage.

- Frontend : http://localhost:5173
- API : http://localhost:8000/api/
- Admin Django : http://localhost:8000/admin/

### Identifiants par défaut

```
utilisateur : admin
mot de passe: admin123
```

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
```

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
docker compose run --rm --entrypoint python backend manage.py test core
```

## Variables d'environnement

| Variable | Défaut | Rôle |
|----------|--------|------|
| `DJANGO_DEBUG` | `0` | `1` active le mode debug (dev uniquement) |
| `DJANGO_SECRET_KEY` | — | **obligatoire** hors mode debug |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | hôtes autorisés, séparés par des virgules |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | origines autorisées |
| `DJANGO_SECURE_SSL_REDIRECT` | `1` | redirection HTTPS hors mode debug |
| `POSTGRES_*` | voir `docker-compose.yml` | connexion à la base |

## Capture d'écran (revue visuelle)

Un script Playwright est fourni pour générer des captures des principaux
écrans (utile si le modèle hôte ne lit pas les images) :

```bash
cd frontend
npx playwright install chromium
npx tsx scripts/screenshot.ts
# → /tmp/shot_login.png, shot_countries.png, shot_detail_equipes.png, …
```