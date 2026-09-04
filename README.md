# JUSTI INNOV — plateforme de contrôle budgétaire

Suivi budgétaire centralisé et traçable des filiales africaines du groupe
INNOV PHARMA : référentiel pays et organisations, comptes et périmètres,
enveloppes annuelles, dossiers de justification, dépenses, pièces
justificatives, circuit de justification, tableaux de bord temps réel,
alertes, imports et exports, supervision.

Les règles que le code doit respecter sont dans [`CLAUDE.md`](CLAUDE.md) ;
le modèle de données et les décisions prises, dans
[`docs/model-de-donnees.md`](docs/model-de-donnees.md) ; le serveur, la
supervision et les sauvegardes, dans [`deploy/README.md`](deploy/README.md).
L'équipe de développement compte une seule personne : ces trois documents
sont écrits pour être suffisants.

## Périmètre

Dix-sept filiales : Sénégal, Mali, Côte d'Ivoire, Madagascar, Cameroun,
Gabon, Mauritanie, Burkina Faso, Niger, Bénin, Guinée, Togo, Gambie,
Djibouti, Tchad, Congo et République démocratique du Congo. La liste est
dans `backend/core/africa.py` : un pays se crée depuis elle, tout autre code
ISO est refusé, et l'ouvrir à une nouvelle filiale se fait dans ce fichier.
Au démarrage, seules la Côte d'Ivoire et le Togo sont créées ; les autres le
seront à leur entrée dans le dispositif.

## Architecture

| Service   | Techno                                        | Port (127.0.0.1) |
|-----------|-----------------------------------------------|-------|
| Backend   | Django 5.2 + Django REST Framework + gunicorn | 8000  |
| Frontend  | React 19 + TypeScript + Vite + Tailwind v4 + shadcn/ui | 5173  |
| Base      | PostgreSQL 16                                 | 5433  |
| Stockage  | MinIO (justificatifs, API S3)                 | 9000, console 9001 |
| Ordonnanceur | `manage.py run_scheduler` (alertes, rapports) | —  |
| Supervision (production) | Prometheus + Grafana, sur `/grafana/` | — |

En développement, les ports ne sont ouverts que sur la boucle locale. La
supervision n'existe que dans la pile de production
(`deploy/docker-compose.prod.yml`).

Applications Django :

| App        | Rôle |
|------------|------|
| `core`     | Référentiel (pays, managers, équipes, centres de coûts, projets, intitulés, catégories) et historique |
| `accounts` | Profils, rôles, périmètres pays et équipes, double authentification, langue |
| `budget`   | Enveloppes annuelles, sous-enveloppes, réallocations, taux de change |
| `expenses` | Dossiers (N°ORDRE), dépenses, justificatifs, circuit et réouverture, audit |
| `notifications` | Notifications in-app et e-mail |
| `reporting` | Tableaux de bord, alertes, imports et exports (administrateurs) |

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

Cinq rôles, calqués sur l'organisation du groupe :

| Rôle | Libellé | Qui | Périmètre | Peut |
|------|---------|-----|-----------|------|
| `manager` | Manager (pays) | responsable dans une filiale | son pays, restreint à ses équipes (`UserProfile.teams`) ; sans équipe rattachée, tout son pays | saisir ses dépenses, déposer les justificatifs, **soumettre** (déclarer) ; le référentiel de son pays est tenu par la RH |
| `dm` | DM — directeur manager (siège) | au siège | tous pays, **restrictible** à certains | **mettre en contrôle** une dépense soumise (`review_expenses`) ; lire l'historique du référentiel de son périmètre |
| `df` | DF — directeur financier (siège) | au siège | tous pays, **restrictible** à certains | mettre en contrôle, contrôler les pièces, **justifier ou non**, clôturer (`validate_expenses`) ; lire l'historique du référentiel de son périmètre |
| `admin` | Administrateur (RH) | ressources humaines, au siège | tous pays, toujours | tout le circuit, comptes et rôles, pays et référentiel de tous les pays, **journal d'audit**, **imports et exports**, **réouverture** d'un dossier, réinitialisation de la double authentification |
| `super_admin` | Super administrateur (DG, DO, CEO, DEV) | direction et développeurs | tous pays, toujours | tout, et seul à écrire **les enveloppes, les réallocations et les taux de change** ; le back-office Django |

Il n'y a ni « direction des opérations » ni « auditeur » distincts : la DO
est super administratrice, l'audit revient à la RH.

**Le DM et le DF n'ont aucun droit d'administration** — décision du
produit : ils ne sont ni administrateurs ni super administrateurs. Ils
gardent leurs seules fonctions de contrôle (`REVIEW_ROLES` pour le DM,
`VALIDATION_ROLES` pour le DF) et la lecture de l'historique du
référentiel (`HISTORY_READ_ROLES`). Comptes, pays, référentiel, fichiers,
réouverture et journal d'audit relèvent de la RH et de la direction ;
enveloppes, réallocations, taux de change et validation d'un dépassement,
de la direction seule.

Les rôles portent la matrice complète dans `accounts/permissions.py` :
`BUDGET_WRITE_ROLES` (enveloppes, réallocations, taux : `super_admin`),
`AUDIT_READ_ROLES` (journal d'audit : `super_admin`, `admin`),
`EXPORT_ROLES` (imports et exports : `super_admin`, `admin`),
`REOPEN_ROLES` (réouverture : `super_admin`, `admin`). `/api/permissions/`
la renvoie telle qu'elle est appliquée, et `/api/me/` la traduit en
capacités (`record_expenses`, `review_expenses`, `validate_expenses`…) que
l'interface se contente de lire.

**Le manager déclare, le DM contrôle, le DF constate.** Le circuit est
tenu par trois personnes : le `manager` soumet, le `dm` met en contrôle,
le `df` tranche — justifie, refuse ou clôture. Un `manager` ne peut ni
justifier, ni déclarer non justifiée, ni mettre en contrôle, ni clôturer
une dépense — pas même les siennes. Autrement, il pourrait décaisser puis
se donner quitus, ce qui viderait l'application de sa raison d'être. Un
`dm` ne constate pas ; un `df` ne met pas en contrôle. `admin` et
`super_admin` peuvent tout.

La séparation vaut aussi **à l'intérieur du siège** : celui qui a saisi une
dépense ne peut pas la justifier lui-même. Il faut deux personnes.

Le référentiel d'un pays — équipes, projets, intitulés, catégories,
bénéficiaires — est tenu par la RH et les super administrateurs pour tous
les pays (`manage_subentities`) ; ni le `manager`, ni le `dm`, ni le `df`
n'y écrivent.

Le périmètre est porté par le profil : un compte du siège sans pays
explicite couvre tous les pays ; `dm` et `df` peuvent être restreints à
certains, `admin` et `super_admin` jamais. Un `manager` **sans** périmètre
ne voit rien — l'absence de périmètre ne vaut jamais autorisation générale.
Un pays hors périmètre répond 404, sans révéler son existence.

### Double authentification et adresses professionnelles

Chaque compte peut se protéger par un code à usage unique (TOTP, RFC 6238)
en plus de son mot de passe : un mot de passe seul, réutilisé ou
intercepté, suffirait à signer une justification au nom d'un autre. **Elle
est facultative par défaut** — la direction a reporté son obligation — et
se propose depuis le menu du compte (« Activer la double authentification ») :
le titulaire scanne un QR avec son application d'authentification et
saisit un premier code ; le secret n'est remis qu'une fois. Un compte
enrôlé présente ensuite son code à chaque connexion, et le menu le montre
(« 2FA active »). Elle est recommandée à qui contrôle ou justifie.

`DJANGO_TOTP_REQUIRED=1` l'impose à tous : la plateforme reste alors
fermée à un compte non enrôlé jusqu'à son premier code, comme avec un mot
de passe provisoire. La politique se lit dans `GET /api/me/`
(`totp_required`, aux côtés de `totp_confirmed`) ; l'interface n'y redirige
que si les deux le demandent. Un titulaire qui perd son téléphone s'adresse
à un administrateur, seul à pouvoir réinitialiser l'enrôlement ;
l'opération est journalisée (voir `deploy/README.md`).

Dans l'API : quand elle est imposée, toute route répond `403
{"totp_setup_required": true}` tant que le compte n'est pas enrôlé, après
le mot de passe provisoire ; `POST /api/me/2fa/enrol/` renvoie
`otpauth_uri`, `qr_png_base64` et `secret`, `POST /api/me/2fa/confirm/
{code}` valide le premier code (`ChangeLog` `totp_confirmed`). Pour un
compte enrôlé, `POST /api/token-auth/` attend `{username, password, code}`
et répond `400 totp_required` si le code manque ou est faux — l'échec est
journalisé (`login_failed`, `changed_fields: ["totp"]`) ; le champ
« Code » de l'écran de connexion reste visible et facultatif pour les
autres. `POST /api/users/{id}/reset-2fa/` efface l'enrôlement
(`totp_reset`) ; réservé aux administrateurs, dans le respect de la
hiérarchie. Pour un environnement jetable (CI, démonstration), `seed_users`
accepte une clé `totp_secret` qui enrôle et confirme d'emblée : à ne jamais
utiliser sur un serveur réel.

Chaque compte porte une adresse professionnelle : un domaine hors de
`ALLOWED_EMAIL_DOMAINS` (`innovpharma.net` par défaut) est refusé à la
création du compte.

### Langues

L'interface est bilingue, français et anglais. Le serveur répond dans la
langue de l'en-tête `Accept-Language` ; l'interface l'envoie d'après la
préférence enregistrée sur le profil (`UserProfile.language`, français par
défaut), que l'utilisateur change depuis le menu de son compte. Les textes
du serveur passent par `gettext` et les catalogues `locale/en` des six
applications Django, notifications et e-mails compris, rendus dans la
langue du destinataire ; les `.po` sont versionnés, les `.mo` compilés à la
construction de l'image et au démarrage du conteneur de développement
(`backend/entrypoint.sh`), jamais dans le dépôt. Il n'y a pas de variable
d'environnement pour la langue : la référence est le français
(`LANGUAGE_CODE`).

### Application de bureau (PWA)

L'application se sert dans un navigateur et s'installe comme application de
bureau (manifeste et service worker de Vite). L'usage sur téléphone n'est pas
un cas prévu : les écrans sont conçus pour un poste de travail, et les
captures de `DESIGN.md` ne vérifient que le grand écran — l'écran de
connexion mis à part.

### Fichiers : imports et exports réservés aux administrateurs

L'import du classeur Excel et les exports — Excel, CSV, Word et PDF, classés
par exercice ou par mois — sont réservés à `admin` et `super_admin`. Tous les
autres travaillent dans l'application : un fichier sorti du système n'est
plus ni calculé ni tracé, et un fichier entré contourne la saisie ligne à
ligne. Chaque export laisse une entrée dans le journal d'audit. La
conservation est illimitée : rien n'est jamais purgé, ni dossier, ni pièce,
ni journal, et les sauvegardes suivent la même règle (copie mensuelle gardée
pour toujours).

Les exports prennent `year` (exercice), `month` facultatif (1 à 12, pour un
classement par mois) et `country`. Le CSV est en UTF-8 avec BOM, séparateur
`;`, pour s'ouvrir tel quel dans Excel ; les totaux ne figurent que si une
seule devise est concernée — additionner deux devises serait un chiffre
faux. Le rapport périodique envoyé par l'ordonnanceur n'attache le classeur
qu'aux administrateurs ; les autres reçoivent le message sans pièce jointe.

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
POST   /api/token-auth/                  # obtention du jeton {username, password, code} ; 400 totp_required sans code valide
POST   /api/logout/                      # révocation du jeton
GET    /api/me/                          # rôle, périmètre, droits, politique 2FA (totp_required) et enrôlement (totp_confirmed)
POST   /api/me/password/                 # changement de mot de passe
GET    /api/permissions/                 # matrice rôle × action, telle que le serveur l'applique
GET/PATCH /api/configuration/            # réglages de la plateforme (siège)
GET/PATCH /api/workflow-configuration/   # politique du circuit : étape de contrôle, seuils, dépassement
GET/POST/PATCH /api/users/               # comptes (administrateurs)
POST   /api/users/{id}/reset-2fa/        # efface l'enrôlement TOTP (administrateurs, hiérarchie respectée)
POST   /api/me/2fa/enrol/                # {otpauth_uri, qr_png_base64, secret} — une seule fois
POST   /api/me/2fa/confirm/              # {code} : premier code valide, la plateforme s'ouvre

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

GET/POST/PATCH /api/budgets/             # enveloppes annuelles et sous-enveloppes (?year=) ; écriture : super_admin
GET    /api/budgets/summary/             # consolidation par pays, total en FCFA
GET/POST /api/reallocations/             # demandes de transfert entre enveloppes (super_admin)
POST   /api/reallocations/{id}/approve/  # exécute le transfert (super_admin)
POST   /api/reallocations/{id}/reject/   # motif obligatoire (super_admin)
GET/POST/PATCH /api/exchange-rates/      # taux de conversion vers le FCFA ; écriture : super_admin

GET/POST/PATCH /api/dossiers/            # dossiers de justification (N°ORDRE)
DELETE /api/dossiers/{id}/               # brouillon seul, par son auteur
POST   /api/dossiers/{id}/submit/        # soumet le dossier et ses lignes (avertit s'il n'a pas de pièce)
POST   /api/dossiers/{id}/review|justify|reject|close/  # review : DM ; justify, reject, close : DF
POST   /api/dossiers/{id}/reopen/        # réouverture {note} : administrateurs, motif obligatoire
GET/POST/PATCH /api/expenses/            # lignes de dépenses
DELETE /api/expenses/{id}/               # brouillon seul, par son auteur
POST   /api/expenses/{id}/review|justify|reject|close/
GET    /api/expenses/register/           # registre : chaque dépense et ses preuves
GET/POST /api/proofs/                    # justificatifs (dépôt multipart)
GET    /api/proofs/{id}/download/        # téléchargement contrôlé et tracé
POST   /api/proofs/{id}/review/          # contrôle documentaire
GET/POST/PATCH /api/beneficiaries/       # prospects et bénéficiaires, par pays
GET    /api/audit/                       # journal d'audit : RH et direction (admin, super_admin)

GET    /api/dashboard/                   # consolidation, charge et alertes
GET    /api/dashboard/breakdown/         # répartition équipe/manager/projet/mois
GET    /api/exports/expenses.{xlsx,csv,docx}        # registre au format du fichier historique
GET    /api/exports/reconciliation.{xlsx,csv,docx}  # rapprochement dépenses / justifiés
GET    /api/exports/report.pdf                      # rapport de synthèse
                                         # ?year= ?month= (1-12, facultatif) ?country= ; administrateurs seulement
POST   /api/imports/expenses.xlsx        # import : export de la plateforme ou classeur historique (administrateurs)
GET    /metrics                          # collecte Prometheus, jeton METRICS_TOKEN en Authorization: Bearer
GET    /api/notifications/               # centre de notifications
GET    /api/notifications/unread_count/
POST   /api/notifications/{id}/read/ · /api/notifications/read-all/
```

`review`, `justify`, `reject`, `close` et `reopen` sont les transitions du
circuit de justification (voir plus bas) ; `reject` et `reopen` exigent un
motif.

Les listes acceptent `?country__country_ref=TG-02` pour cibler un pays par
son identifiant fonctionnel, ainsi que `?status=` et `?search=` ; `?year=`
vaut pour les enveloppes. Le registre accepte en plus `?date__gte=` et
`?date__lte=` pour une période. Toutes les listes sont paginées : `?page=` et
`?page_size=` (plafonné à 200).

Toutes les listes sont filtrées par le périmètre du compte — par pays, et,
pour un `manager` rattaché à des équipes, par équipe (`team__in` sur les
dossiers, les dépenses, les pièces via leur dossier, et les équipes
elles-mêmes ; `CountryScopedMixin.team_lookup`). Les exports et le
téléchargement d'une pièce sont les seules requêtes `GET` qui écrivent :
elles laissent une entrée dans le journal d'audit (`downloaded`, avec
`year`, `month`, `country` et `format` pour un export), parce qu'une donnée
qui sort du système doit laisser une trace.

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
| Backend | migrations à jour, traductions compilées, `check --deploy`, suite Django hors mode debug |
| Frontend | types, lint, tests unitaires, build |
| Images Docker | les deux images se construisent |
| Parcours complet | la pile livrable (backend en production, frontend nginx) démarre, des comptes jetables s'y connectent, les trois scripts de capture de `DESIGN.md` (parcours, connexion, thème sombre) passent sans erreur de console, et la limitation de débit de nginx répond bien 429 en JSON sous une rafale ; les captures sont publiées en artefact |
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
`/api/health/` répond depuis l'extérieur. Le dossier `deploy/` est copié en
entier sur le serveur : pile, Caddyfile, scripts de sauvegarde et de
restauration, configuration Prometheus et provisioning Grafana. La
préparation du serveur, les secrets attendus, la coupure pendant les
migrations, le retour arrière, le rôle Postgres à moindre privilège, la
supervision et les sauvegardes sont décrits dans
[`deploy/README.md`](deploy/README.md).

Les mises à jour de dépendances arrivent en PR via Dependabot
(`.github/dependabot.yml`), donc passent par la CI.

## Déploiement, supervision et sauvegardes

En production, nginx limite `/api/` à 20 requêtes par seconde et par
adresse (réserve de 40) et répond `429` avec un `detail` en français ;
Django garde sa propre limite, plus stricte, sur l'obtention du jeton. Le
service Django peut tourner avec un rôle Postgres sans droit sur le schéma
(`deploy/creer_role_applicatif.sql`), les migrations gardant le rôle
propriétaire.

**Supervision en temps réel.** Prometheus collecte toutes les quinze
secondes les compteurs du backend (`django-prometheus`, exposés sur
`/metrics` sous le jeton `METRICS_TOKEN`), ceux de la base
(`postgres-exporter`) et ceux du serveur (`node-exporter`) ; Grafana les
affiche sur `https://<domaine>/grafana/`, sur un tableau de bord
provisionné depuis `deploy/grafana/dashboards/justi-innov.json` :
requêtes par seconde et latence par vue, erreurs 5xx, connexions et taille
de la base, processeur, mémoire et disque du serveur, état des cibles de
collecte. Grafana est **partagé avec la direction et l'équipe technique** :
outre l'administrateur (`GRAFANA_ADMIN_PASSWORD`), un compte « direction »
en lecture seule et un compte « technique » en édition, créés à la mise en
service (`deploy/README.md`) ; le tableau de bord de la plateforme est la
page d'accueil de chacun. Les administrateurs de l'application y accèdent
par l'entrée « Supervision » du menu de leur compte, qui ouvre `/grafana/`
dans un nouvel onglet — Grafana a ses propres comptes, distincts de ceux de
l'application.

**Sauvegardes.** La pile sauvegarde chaque nuit la base (`pg_dump -Fc`) et
met en miroir le bucket des justificatifs dans le volume `sauvegardes`. Les
dumps quotidiens sont gardés 30 jours ; le premier dump de chaque mois est
copié dans `base/mensuel/` et **n'est jamais supprimé** — la conservation
des données est illimitée, celle des sauvegardes aussi. `deploy/restaurer.sh`
restaure un dump, dans la pile ou dans une base jetable pour le test
trimestriel. Le volume reste sur la machine : sa copie ailleurs est à
organiser. Tout est décrit dans [`deploy/README.md`](deploy/README.md).

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
| `DJANGO_TOTP_REQUIRED` | `0` | `1` impose la double authentification à tous les comptes (plateforme fermée jusqu'à l'enrôlement) ; `0` la propose depuis le menu du compte. Exposée par `GET /api/me/` (`totp_required`) |
| `ALLOWED_EMAIL_DOMAINS` | `innovpharma.net` | domaines de messagerie admis pour les comptes, séparés par des virgules ; ne peut pas être vide |
| `METRICS_TOKEN` | — | jeton que Prometheus présente sur `/metrics` (`Authorization: Bearer`) ; vide, le point de collecte répond 404 |
| `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` | `admin` / — | compte d'administration de Grafana (pile de production) ; le mot de passe est **obligatoire**. Les comptes « direction » et « technique » se créent depuis lui (`deploy/README.md`) |
| `DJANGO_TIME_ZONE` | `UTC` | fuseau de référence du serveur |
| `DJANGO_CREATE_SUPERUSER` | `0` | `1` crée un compte d'amorçage au démarrage, profil `super_admin` et mot de passe provisoire |
| `DJANGO_SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` | `admin` / — / — | identité de ce compte ; sans mot de passe, rien n'est créé |
| `POSTGRES_HOST` / `_PORT` / `_DB` / `_USER` / `_PASSWORD` | `db` / `5432` / `justi_innov` / `justi` / `justi` | connexion à la base (le mot de passe est **obligatoire** hors mode debug) |
| `DATABASE_URL` | — | `postgresql://utilisateur:motdepasse@hôte:port/base?sslmode=…` ; si définie, prime sur les `POSTGRES_*`. Parseur maison (`config.settings.parse_database_url`) : les paramètres de la chaîne de requête vont dans `OPTIONS`, le mot de passe est décodé |
| `POSTGRES_MIGRATION_USER` / `_PASSWORD` | — | rôle propriétaire avec lequel `migrate` et `createcachetable` tournent au démarrage, quand `POSTGRES_USER` est le rôle applicatif sans DDL (`deploy/creer_role_applicatif.sql`) |
| `DATABASE_MIGRATION_URL` | — | même chose, sous forme d'URL, quand la base est désignée par `DATABASE_URL` |
| `SAUVEGARDE_HEURE` / `SAUVEGARDE_PIECES_HEURE` / `SAUVEGARDE_RETENTION_JOURS` | `02:00` / `02:15` / `30` | heure UTC du `pg_dump` et du miroir des justificatifs, rétention des dumps quotidiens (pile de production) ; la copie mensuelle n'expire jamais |
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
petit écran, et les écrans principaux dans les deux thèmes. Les identifiants
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
    ↑          │           │              │ (non justifié)
    └──────────┴───────────┴──────────────┘  réouverture (administrateur, motif)
```

Côté pays, déclarer une dépense tient en **une action** : le manager
remplit les lignes, joint le justificatif, soumet le dossier — ses lignes
partent avec lui. Le reste est calculé par le système et relève du siège :
**le manager soumet, le DM met en contrôle, le DF tranche** — justifie,
refuse ou clôture. L'étape de contrôle est facultative sauf si la politique
du circuit l'impose (`require_review_step`).

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

La **réouverture** est la seule exception, et elle est faite pour demander
des comptes, pas pour corriger en silence : un administrateur (`admin`,
`super_admin`) renvoie au brouillon un dossier déclaré mais pas encore
constaté, avec un motif (`note`), conservé sur le dossier (`reopen_note`)
et dans le journal d'audit (`reopened`, sur le dossier et sur chaque
ligne) ; les lignes reviennent en brouillon et perdent leur imputation
(`budget = null`), recalculée à la prochaine soumission ; les comptes qui
suivent le pays en sont notifiés (`dossier_reopened`) et le dossier devra
être soumis à nouveau. Elle est refusée dès
qu'une ligne du dossier est justifiée ou clôturée : le siège a constaté, et
un constat ne se défait pas. Ni le pays qui a déclaré ni la direction
financière qui constate ne peuvent rouvrir.

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
justification aux super administrateurs (la direction) — le pays pouvant dans
tous les cas déclarer la dépense.

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

## Import Excel et N°ORDRE

`POST /api/imports/expenses.xlsx` (champ `file`, administrateurs seulement)
lit deux classeurs : l'export de la plateforme, et le **classeur historique du
client** — feuille « BASE DE DONNEES ACTIONS », titre et note en tête,
en-tête en septième ligne, neuf colonnes (N°ORDRE, DATE, TEAM, OWNER,
LIBELLE DES TRANSACTIONS, DEPENSES, MONTANT JUSTIFIER, ECART, PIECES
JUSTIFICATIVES). La ligne d'en-tête est reconnue à son contenu dans les
quinze premières lignes ; seules ces six premières colonnes sont
obligatoires.

- Le classeur historique est mono-pays : passez le pays en paramètre,
  `?country=<id>` (ou champ de formulaire `country`). Il est vérifié contre
  le périmètre du compte ; un pays inconnu et un pays hors périmètre reçoivent
  le même refus. Avec une colonne PAYS, le paramètre sert de repli aux
  cellules vides.
- Le **N°ORDRE est unique par pays**, comme dans le classeur : le « 12 » du
  Togo et le « 12 » de la Côte d'Ivoire sont deux dossiers. Une ligne rejoint
  le dossier de son pays s'il est encore en brouillon, sinon elle le crée ;
  un entier est lu en texte (« 12 », jamais « 12.0 »).
- Tout arrive en **brouillon**, sans montant justifié : MONTANT JUSTIFIER,
  ECART et STATUT sont ignorés — le siège constate. La mention de la colonne
  PIECES JUSTIFICATIVES est gardée en remarque de la ligne
  (« Pièce : Reçu(justif incomplet) ») ; la pièce elle-même se dépose ensuite
  sur le dossier.
- Une équipe ou un manager que le pays ne connaît pas est **créé dans le
  pays** (et journalisé dans l'historique) ; un homonyme d'un autre pays n'est
  jamais réutilisé. `?dry_run=true` valide tout, compte ce qui serait créé
  (`dossiers_crees`, `lignes_creees`, `equipes_creees`, `managers_crees`) et
  n'écrit rien.
- Rien n'est écrit tant qu'une ligne est en erreur ; chaque erreur porte le
  numéro de ligne **du classeur**, tel qu'Excel l'affiche. Réimporter le même
  fichier ne crée rien.
- À la soumission d'un dossier, chaque ligne doit porter une équipe et un
  manager : l'import les fournit, une saisie manuelle doit les compléter.
