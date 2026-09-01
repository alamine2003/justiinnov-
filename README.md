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

Chaque entrée conserve `label`, `performed_by` (utilisateur authentifié),
`from_value` / `to_value` et `created_at`.

## Capture d'écran (revue visuelle)

Un script Playwright est fourni pour générer des captures des principaux
écrans (utile si le modèle hôte ne lit pas les images) :

```bash
cd frontend
npx playwright install chromium
npx tsx scripts/screenshot.ts
# → /tmp/shot_login.png, shot_countries.png, shot_detail_equipes.png, …
```