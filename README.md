# Plateforme de contrôle budgétaire

Suivi budgétaire centralisé et traçable : référentiel pays et organisations,
comptes et périmètres, enveloppes annuelles, dossiers de justification,
dépenses, pièces justificatives, workflow de validation, tableaux de bord
temps réel, alertes et exports.

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
| `owner` | ses pays | saisir ses dépenses et déposer les justificatifs |

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
GET/POST/PATCH/DELETE /api/expenses/     # lignes de dépenses (DELETE : brouillon seul)
GET    /api/expenses/register/           # registre : chaque dépense et ses preuves
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
Le registre accepte en plus `?date__gte=` et `?date__lte=` pour une période.
Toutes les listes sont paginées : `?page=` et `?page_size=` (plafonné à 200).

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
