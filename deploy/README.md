# Déploiement de JUSTI INNOV

La livraison continue (`.github/workflows/cd.yml`) livre `main` en
préproduction et les tags `v*` en production, après approbation. Ce dossier
est copié en entier sur le serveur à chaque livraison ; il contient tout ce
qu'il faut pour exploiter la plateforme sans autre document — l'équipe de
développement compte une seule personne, ce fichier doit se suffire.

```
main ──────▶ CI ──▶ images ghcr.io ──▶ staging      (automatique)
tag v1.2.3 ▶ CI ──▶ images ghcr.io ──▶ production   (approbation requise)
```

| Fichier | Rôle |
|---|---|
| `docker-compose.prod.yml` | la pile : Postgres, MinIO, backend, ordonnanceur, frontend, Caddy, sauvegardes, supervision (Prometheus, exporteurs, Grafana) |
| `Caddyfile` | entrée publique, TLS automatique, route `/grafana/` |
| `prometheus/prometheus.yml` | cibles de collecte : backend (sous jeton), base, serveur |
| `grafana/provisioning/` | source de données Prometheus et chargement des tableaux de bord au démarrage de Grafana |
| `grafana/dashboards/justi-innov.json` | le tableau de bord de la plateforme |
| `deploy.sh` | tire une étiquette d'images, relance la pile, attend qu'elle soit saine |
| `.env.example` | modèle du `.env` du serveur, jamais versionné |
| `creer_role_applicatif.sql` | rôle Postgres du service, sans droit de modifier le schéma |
| `sauvegarder.sh` | sauvegarde nocturne de la base (30 jours de quotidiens, copie mensuelle conservée sans limite) et des justificatifs, dans le volume `sauvegardes` |
| `restaurer.sh` | restaure un dump dans la pile ou dans une base jetable, et remet les justificatifs |

## Préparer un serveur

1. Une machine Linux avec Docker Engine et le plugin Compose (v2.24 ou plus),
   les ports 80 et 443 ouverts, un enregistrement DNS vers elle.
2. Un utilisateur dédié, membre du groupe `docker`, avec une clé SSH
   réservée au déploiement :
   ```bash
   sudo adduser --disabled-password deploy && sudo usermod -aG docker deploy
   sudo -u deploy mkdir -p ~deploy/.ssh ~deploy/justi-innov
   # ajoutez la clé publique dans ~deploy/.ssh/authorized_keys
   ```
3. Le fichier `.env` dans `~deploy/justi-innov/`, d'après `.env.example`,
   en `chmod 600`. Quatre secrets s'y génèrent, avec
   `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` :
   `DJANGO_SECRET_KEY` (64 plutôt que 32), `POSTGRES_PASSWORD`,
   `AWS_SECRET_ACCESS_KEY`, `METRICS_TOKEN` ; plus `GRAFANA_ADMIN_PASSWORD`,
   que vous taperez dans un navigateur. `ACME_EMAIL` est obligatoire : vide,
   Caddy refuse sa configuration et rien ne démarre.
4. Dans GitHub, un environnement `staging` et un environnement `production`
   (Settings › Environments) portant chacun :

   | Type | Nom | Contenu |
   |---|---|---|
   | secret | `DEPLOY_HOST` | hôte SSH |
   | secret | `DEPLOY_USER` | `deploy` |
   | secret | `DEPLOY_SSH_KEY` | clé privée correspondante |
   | secret | `DEPLOY_KNOWN_HOSTS` | sortie de `ssh-keyscan -H <hôte>`, **obligatoire** : le workflow refuse de partir sans, plutôt que d'accepter l'empreinte de n'importe quelle machine au premier contact |
   | variable | `APP_DOMAIN` | domaine public |
   | variable | `DEPLOY_PATH` | `~/justi-innov` par défaut |

   Sur `production`, réglez deux choses — c'est là, et pas dans le workflow,
   que se décide qui déploie quoi :

   - **Required reviewers** : les relecteurs dont l'approbation est attendue
     avant que le travail `Déployer (production)` ne démarre.
   - **Deployment branches and tags → Selected branches and tags**, avec la
     seule règle `v*`. Sans elle, un `workflow_dispatch` depuis n'importe
     quelle branche pourrait viser la production ; avec elle, GitHub refuse
     le travail avant même de demander une approbation.

   Sur `staging`, aucune règle : `main` part seule.

   Les valeurs transmises au serveur (étiquette, noms d'images, domaine,
   chemin) sont vérifiées par expression régulière avant tout appel SSH, et
   passent par un fichier `.deploy-env` lu puis effacé sur le serveur ; le
   jeton de registre, lui, ne transite que par l'entrée standard.

## Ce qui se passe pendant un déploiement

`deploy.sh` tire les images, puis `docker compose up --wait` remplace les
conteneurs. **Le backend est indisponible le temps des migrations** : le
conteneur précédent est arrêté, le nouveau applique `migrate` avant de
lancer gunicorn, et nginx répond 502 sur `/api/` entre les deux — quelques
secondes en général, plus si une migration réécrit une grosse table. Le
frontend statique, lui, reste servi. Prévenez les pays avant une livraison
en heures ouvrées si le journal des migrations est long.

Le conteneur dispose d'un **délai de grâce de 90 s** (`start-period` du
`HEALTHCHECK` de `backend/Dockerfile`) avant que ses échecs de santé ne
comptent, et `--wait` attend jusqu'à 240 s que tous les services soient
sains. Une migration plus longue que cela fait échouer le déploiement et
déclenche le retour arrière décrit plus bas, qui remplace le conteneur en
cours de migration : Postgres annule alors la transaction de la migration
interrompue, la base reste cohérente. Faites tourner la migration longue à
la main, puis redéployez :

```bash
docker compose -f docker-compose.prod.yml run --rm --entrypoint python \
    backend manage.py migrate
```

Les `mem_limit` de `docker-compose.prod.yml` sont taillés pour une machine
de 4 Go : la plateforme reste sous 3 Go, la supervision ajoute 640 Mo de
plafond — 8 Go sont plus confortables ; `GUNICORN_WORKERS` et
`GUNICORN_THREADS` dans `.env` se règlent d'après le nombre de cœurs (voir
`.env.example`).

Une livraison peut être rejouée sans nouvelle image : `deploy.sh` avec la
même étiquette recharge la configuration copiée (Caddyfile, Prometheus,
tableaux de bord Grafana), puisque ces fichiers sont montés depuis ce
dossier et non copiés dans les images.

## Première mise en service

Une fois la pile en ligne, les comptes se créent depuis le serveur, à partir
d'un fichier qui ne quitte jamais la machine :

```bash
cd ~/justi-innov
docker compose -f docker-compose.prod.yml cp seed_users.json backend:/tmp/seed.json
docker compose -f docker-compose.prod.yml exec backend \
    python manage.py seed_users --file /tmp/seed.json
```

Chaque compte porte une adresse en `ALLOWED_EMAIL_DOMAINS`
(`innovpharma.net`), un mot de passe provisoire, et s'enrôle à la double
authentification à sa première connexion (voir plus bas). Seules la Côte
d'Ivoire et le Togo existent au départ ; les quinze autres filiales se
créent depuis l'écran des pays, parmi les codes de `backend/core/africa.py`.

Vérifiez ensuite la supervision : `https://<domaine>/grafana/` demande le
compte `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`, et le tableau de
bord « JUSTI INNOV — supervision » doit montrer ses quatre cibles « en
ligne ». Une cible `backend` « hors ligne » alors que l'API répond signifie
presque toujours un `METRICS_TOKEN` vide ou différent entre `.env` et le
conteneur (relancez la pile après l'avoir changé).

## Double authentification : réinitialiser un enrôlement

Tout compte doit présenter un code TOTP en plus de son mot de passe, et la
plateforme reste fermée à un compte non enrôlé. Un titulaire qui a perdu son
téléphone ou son application ne peut donc plus rien faire, et personne ne
peut lui « donner » un code : le secret n'a été remis qu'à lui.

Seul un administrateur (`admin` ou `super_admin`) réinitialise l'enrôlement,
depuis la fiche du compte dans l'écran des comptes (`POST
/api/users/{id}/reset-2fa/`, dans le respect de la hiérarchie : un `admin`
ne réinitialise pas un `super_admin`) : le secret est effacé, le titulaire
refait l'enrôlement à sa prochaine connexion, et l'opération est inscrite
dans l'historique (`ChangeLog`, action `totp_reset`) avec l'auteur et
l'adresse d'où elle a été faite. Les échecs de code se lisent au même
endroit (`login_failed`, champ `totp`) : une série d'échecs sur un compte
est à regarder avant de le réinitialiser. Faites-la précéder d'une vérification
d'identité par un autre canal — un appel, pas un e-mail : c'est exactement
le cas où un compte de messagerie compromis chercherait à se faire
réinitialiser.

Les administrateurs eux-mêmes ne sont pas exemptés. Prévoyez donc **deux
comptes `super_admin`** au moins, pour que l'un puisse réinitialiser
l'autre ; à défaut, la réinitialisation passe par le back-office Django
(`/admin/`, réservé à `super_admin`) ou par le shell, ce qui ne laisse une
trace que dans les journaux du conteneur.

Le fichier de `seed_users` accepte une clé `totp_secret` qui enrôle et
confirme le compte d'emblée : elle sert aux environnements jetables (CI,
démonstration) et **ne doit jamais figurer dans le fichier d'un serveur
réel** — un secret qui a transité par un fichier n'est plus un secret.

## Revenir en arrière

**Automatiquement** : si la nouvelle pile ne devient pas saine dans les
240 s, `deploy.sh` relance la pile avec l'étiquette lue dans `.deployed`,
puis sort en erreur — la livraison échoue, la plateforme reste en ligne sur
la version précédente. Le journal du workflow montre les 100 dernières
lignes du backend fautif. S'il n'y a pas d'étiquette précédente (première
mise en service) ou si le retour échoue lui aussi, le script le dit et
laisse la main.

**À la main** : chaque déploiement écrit l'étiquette livrée dans
`.deployed`. Pour revenir à la précédente, relancez `deploy.sh` avec elle —
l'image est encore sur le serveur et sur le registre :

```bash
IMAGE_TAG=sha-… BACKEND_IMAGE=ghcr.io/<org>/<dépôt>-backend \
FRONTEND_IMAGE=ghcr.io/<org>/<dépôt>-frontend ./deploy.sh
```

Les migrations ne se défont pas seules : ne revenez pas en deçà d'une version
dont la migration a supprimé une colonne. Le retour automatique a la même
limite : un code N-1 lit un schéma N tant que la migration n'a fait
qu'ajouter, ce qui est la règle dans ce projet (rien ne se supprime).

## Rôle Postgres applicatif

Par défaut, le service Django se connecte avec le rôle qui possède la base
(`POSTGRES_USER`, `justi`) : il peut donc tout, y compris supprimer une
table — le journal d'audit, par exemple. `creer_role_applicatif.sql` crée
un second rôle, `justi_app`, qui lit et écrit des lignes mais ne touche pas
au schéma : `CONNECT`, `USAGE` sur le schéma, `SELECT/INSERT/UPDATE/DELETE`
sur les tables et les séquences, présentes et futures (`ALTER DEFAULT
PRIVILEGES`). Ni `CREATE`, ni `DROP`, ni `TRUNCATE`.

Les migrations et `createcachetable`, qui créent des tables, gardent le rôle
propriétaire : `backend/entrypoint.sh` les lance avec
`POSTGRES_MIGRATION_USER` / `POSTGRES_MIGRATION_PASSWORD` quand ces
variables sont définies, puis démarre gunicorn avec `POSTGRES_USER`. Le
conteneur Postgres et les sauvegardes utilisent aussi le propriétaire.

Mise en place, sur une pile déjà en ligne :

```bash
cd ~/justi-innov
MDP_APP="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker compose -f docker-compose.prod.yml exec -T db \
    psql -U justi -d justi_innov -v ON_ERROR_STOP=1 \
    -v role_applicatif=justi_app -v mot_de_passe="$MDP_APP" \
    -f - < creer_role_applicatif.sql
```

Puis dans `.env`, l'ancien couple devient celui des migrations et le
nouveau celui du service :

```
POSTGRES_MIGRATION_USER=justi
POSTGRES_MIGRATION_PASSWORD=<l'ancien POSTGRES_PASSWORD>
POSTGRES_USER=justi_app
POSTGRES_PASSWORD=<MDP_APP>
```

et `docker compose -f docker-compose.prod.yml up -d --wait` relance la
pile. Le script est idempotent : le rejouer renouvelle le mot de passe et
les droits, ce que `restaurer.sh` fait de lui-même après une restauration.
Avec une base désignée par `DATABASE_URL`, `DATABASE_MIGRATION_URL` tient le
rôle de `POSTGRES_MIGRATION_USER`.

## Sauvegardes et restauration

Deux services de la pile s'en chargent chaque nuit, dans le volume
`sauvegardes` :

| Service | Quand (UTC) | Quoi |
|---|---|---|
| `sauvegarde` | `SAUVEGARDE_HEURE`, 02:00 | `pg_dump -Fc` de la base dans `base/<base>-<horodatage>.dump` ; les dumps quotidiens de plus de `SAUVEGARDE_RETENTION_JOURS` (30) jours sont supprimés ; le premier dump réussi de chaque mois est copié dans `base/mensuel/<base>-<AAAA-MM>.dump` et **n'est jamais supprimé** |
| `sauvegarde-pieces` | `SAUVEGARDE_PIECES_HEURE`, 02:15 | miroir du bucket des justificatifs dans `pieces/` (`mc mirror --overwrite`, sans suppression : un objet effacé du bucket reste dans la copie) |

La rétention suit la règle de la plateforme : **rien ne se purge**. Les
quotidiens servent à revenir à la veille ou à la semaine dernière ; les
mensuels, à retrouver l'état de la base à n'importe quelle date passée, pour
une vérification ou un litige, même des années plus tard. Ils sont liés en
dur au quotidien correspondant tant que celui-ci existe, puis en sont la
seule copie. Comptez leur place : la base ne fait que croître, et un mensuel
pèse ce qu'elle pèse ce jour-là (le tableau de bord Grafana affiche sa
taille et l'espace disque restant). Les mensuels ne se suppriment pas à la
main non plus : s'ils encombrent, on les déplace vers un autre stockage,
on ne les efface pas.

Les deux tournent avec `sauvegarder.sh`, qui journalise chaque passage
(`docker compose -f docker-compose.prod.yml logs sauvegarde
sauvegarde-pieces`). Une sauvegarde immédiate, avant une opération risquée :

```bash
docker compose -f docker-compose.prod.yml run --rm sauvegarde --une-fois
docker compose -f docker-compose.prod.yml run --rm sauvegarde-pieces --une-fois
./restaurer.sh --lister
```

**Le volume est sur la même machine que la base.** Une sauvegarde qui brûle
avec le serveur n'en est pas une : copiez-le ailleurs chaque nuit, depuis une
autre machine, par exemple avec `rsync` sur le point de montage du volume
(`docker volume inspect justi-innov_sauvegardes --format '{{.Mountpoint}}'`,
lisible par root), ou en tirant un dump précis :

```bash
docker compose -f docker-compose.prod.yml cp \
    sauvegarde:/sauvegardes/base/justi_innov-2026-09-04T020000Z.dump .
```

### Restaurer

`restaurer.sh` prend le nom d'un dump du volume et le restaure avec
`pg_restore --clean --if-exists`, après avoir arrêté le backend et
l'ordonnanceur ; il demande de taper le nom de la base, parce que tout ce
qui a été saisi depuis le dump est perdu. Il affiche ensuite le nombre de
tables, de dépenses et de justificatifs restaurés et la date de la dernière
entrée du journal d'audit, rejoue les droits du rôle applicatif s'il est
en service, et relance la pile :

```bash
./restaurer.sh justi_innov-2026-09-04T020000Z.dump
./restaurer.sh mensuel/justi_innov-2026-08.dump      # depuis une copie mensuelle
```

Les justificatifs se remettent depuis le miroir, dans le bucket, le cas
échéant recréé :

```bash
./restaurer.sh --pieces
```

Restaurez la base **et** les pièces d'une même nuit : une dépense dont la
pièce manque en stockage apparaîtrait justifiée sans preuve.

Avec une base hébergée hors de la pile (`DATABASE_URL`), `sauvegarder.sh`
la sauvegarde bien — `pg_dump` accepte l'URL — mais `restaurer.sh` ne
connaît que le Postgres de la pile : restaurez alors avec `pg_restore` et
la même URL, depuis le conteneur `sauvegarde`.

### Test de restauration trimestriel

Une sauvegarde qu'on n'a jamais restaurée n'est qu'un espoir. Chaque
trimestre, sur le serveur, dans une base jetable — la pile reste en ligne,
rien n'est arrêté :

1. Vérifier que les sauvegardes récentes existent et ont une taille
   plausible (un dump qui pèse quelques kilo-octets est vide) :
   ```bash
   ./restaurer.sh --lister
   docker compose -f docker-compose.prod.yml logs --since 72h sauvegarde sauvegarde-pieces
   ```
2. Restaurer le dernier dump dans une base jetable :
   ```bash
   ./restaurer.sh justi_innov-<horodatage>.dump --base test_restauration
   ```
   Le script crée la base, restaure et affiche les comptages. Comparez-les
   à ceux de la base en service :
   ```bash
   docker compose -f docker-compose.prod.yml exec db psql -U justi -d justi_innov \
       -c 'SELECT count(*) FROM expenses_expense' -c 'SELECT count(*) FROM expenses_proof'
   ```
   Le nombre de dépenses restaurées doit être celui de la veille au soir.
3. Vérifier que les pièces du miroir correspondent aux justificatifs de la
   base restaurée : le miroir doit contenir au moins autant d'objets que la
   base compte de justificatifs.
   ```bash
   docker compose -f docker-compose.prod.yml run --rm --entrypoint sh sauvegarde \
       -c 'find /sauvegardes/pieces -type f | wc -l'
   ```
4. Supprimer la base jetable :
   ```bash
   docker compose -f docker-compose.prod.yml exec db dropdb -U justi test_restauration
   ```
5. Noter la date, le dump testé et les comptages obtenus dans le journal
   d'exploitation. Un écart inexpliqué est un incident, pas une note de bas
   de page.

## Supervision (Prometheus et Grafana)

Quatre services de la pile, sur le réseau interne ; seul Grafana est
atteignable, par Caddy, sur `https://<domaine>/grafana/`, derrière son
propre mot de passe (`GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`).

| Service | Image | Rôle |
|---|---|---|
| `prometheus` | `prom/prometheus:v2.53.5` | collecte toutes les 15 s, garde 90 jours ou 2 Go de mesures (`--storage.tsdb.retention.*`) dans le volume `prometheus_data` |
| `postgres-exporter` | `prometheuscommunity/postgres-exporter:v0.17.1` | connexions, taille, transactions, verrous de la base, avec le rôle applicatif |
| `node-exporter` | `prom/node-exporter:v1.9.1` | processeur, mémoire, disque du serveur (lit `/proc`, `/sys` et `/` de l'hôte, en lecture seule) |
| `grafana` | `grafana/grafana:12.1.1` | affichage ; source de données et tableau de bord provisionnés depuis `grafana/`, volume `grafana_data` pour le reste |

Le backend expose ses compteurs (`django-prometheus`) sur `/metrics`, que
Prometheus interroge directement sur `backend:8000` avec le jeton
`METRICS_TOKEN` en `Authorization: Bearer` — le jeton passe par un secret
Compose (`/run/secrets/metrics_token`), jamais par la ligne de commande ni
par le fichier de configuration. Sans jeton, `/metrics` répond 404 ; avec un
mauvais jeton, 401. Le point n'est pas routé par nginx ni par Caddy : il
n'est pas joignable depuis l'extérieur. `DJANGO_ALLOWED_HOSTS` doit contenir
`backend` en plus du domaine (voir `.env.example`), sans quoi Django répond
400 à Prometheus.

Le tableau de bord « JUSTI INNOV — supervision » (`uid` `justi-innov`) est
en lecture seule dans Grafana : il vient du dépôt. Pour le modifier, faites
la modification dans Grafana, exportez le JSON (Share › Export) et
remplacez `grafana/dashboards/justi-innov.json` ; la livraison suivante — ou
un `deploy.sh` rejoué — le recharge. Il montre :

- l'état des cibles de collecte (`up`) : un backend « hors ligne » alors
  que l'API répond est un problème de jeton ou de `DJANGO_ALLOWED_HOSTS` ;
- le trafic et la latence p95 par vue Django, les réponses par statut, les
  erreurs 5xx et les exceptions, les requêtes SQL par seconde ;
- les connexions à la base (plafond Postgres : 100), sa taille, les
  transactions validées et annulées, les verrous ;
- le processeur, la mémoire, le disque et la charge du serveur.

Ce sont des mesures, pas des données métier : rien du contenu des dossiers
n'y transite, et la rétention de 90 jours ne contredit pas la conservation
illimitée de la plateforme. Il n'y a pas d'alerte automatique depuis
Grafana : les alertes budgétaires viennent de l'application
(`notify_alerts`). Une alerte d'exploitation (disque, 5xx) se pose dans
Grafana › Alerting, avec un canal SMTP réglé par les variables
`GF_SMTP_*` — à ajouter au service `grafana` si vous en avez besoin.

Vérifier la configuration sans lancer la pile :

```bash
docker run --rm -v "$PWD/prometheus/prometheus.yml:/p.yml:ro" \
    --entrypoint promtool prom/prometheus:v2.53.5 check config /p.yml
docker run --rm -e APP_DOMAIN=exemple.org -e ACME_EMAIL=a@exemple.org \
    -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2.8-alpine \
    caddy validate --config /etc/caddy/Caddyfile
docker compose -f docker-compose.prod.yml config >/dev/null   # avec le .env
```

Recharger Prometheus après avoir modifié `prometheus/prometheus.yml`, sans
le redémarrer :

```bash
docker compose -f docker-compose.prod.yml exec prometheus \
    wget -qO- --post-data= http://127.0.0.1:9090/-/reload
```
