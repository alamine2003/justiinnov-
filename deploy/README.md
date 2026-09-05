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
| `docker-compose.prod.yml` | la pile : Postgres, MinIO, backend, ordonnanceur, frontend, Caddy, sauvegardes (base, pièces, copie hors machine) et, sous le profil optionnel `supervision`, Prometheus, exporteurs et Grafana |
| `Caddyfile` | entrée publique, TLS automatique, route `/grafana/` quand `SUPERVISION=1`, 404 sinon |
| `prometheus/prometheus.yml` | cibles de collecte : backend (sous jeton), base, serveur |
| `grafana/provisioning/` | source de données Prometheus et chargement des tableaux de bord au démarrage de Grafana |
| `grafana/dashboards/justi-innov.json` | le tableau de bord de la plateforme |
| `deploy.sh` | vérifie la configuration (`compose config`), tire une étiquette d'images, relance la pile, attend qu'elle soit saine ; sinon montre l'état et les journaux de chaque service non sain et rétablit l'étiquette précédente |
| `.env.example` | modèle du `.env` du serveur, jamais versionné ; aucun service ne le lit en bloc (« Secrets et variables », plus bas) |
| `docker-compose.override.yml` | facultatif, jamais versionné : surcharge locale déclarée par `COMPOSE_FILE` dans `.env` (« Surcharge locale ») |
| `creer_role_applicatif.sql` | rôle Postgres du service, sans droit de modifier le schéma |
| `sauvegarder.sh` | sauvegarde nocturne de la base (30 jours de quotidiens, copie mensuelle conservée sans limite) et des justificatifs, dans le volume `sauvegardes`, puis copie hors machine de chaque sauvegarde réussie vers un stockage objet S3 (`rclone`), vérifiée |
| `restaurer.sh` | restaure un dump dans la pile ou dans une base jetable, et remet les justificatifs — depuis le volume, ou depuis la copie hors machine (`--depuis-distant`) |

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
   que vous taperez dans un navigateur. Les deux derniers ne servent qu'à
   la supervision, mais Compose interpole toute la pile avant d'appliquer
   les profils : `GRAFANA_ADMIN_PASSWORD` doit être renseigné même
   supervision désactivée (« Supervision », plus bas) — générez-le tout de
   suite, il servira le jour de l'activation. `ACME_EMAIL` est obligatoire : vide,
   Caddy refuse sa configuration et rien ne démarre. `EMAIL_HOST` l'est
   aussi : hors mode debug, le backend refuse de démarrer sans serveur SMTP,
   parce que les alertes budgétaires et les rapports partiraient dans les
   journaux sans que personne ne le voie ; une préproduction sans SMTP
   l'acquitte explicitement avec `EMAIL_BACKEND_CONSOLE=1`.
4. **Un stockage objet hors de la machine pour les sauvegardes**, renseigné
   dans `SAUVEGARDE_DISTANT_*` : un bucket S3 compatible chez un autre
   hébergeur ou dans une autre région, avec un compte qui ne peut que lire,
   écrire et lister ce bucket. C'est **obligatoire avant toute mise en
   production** (« Copie hors machine », plus bas) ; une préproduction peut
   s'en passer, `deploy.sh` et les services de sauvegarde le rappellent
   alors à chaque occasion.
5. Dans GitHub, un environnement `staging` et un environnement `production`
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

`deploy.sh` commence par `docker compose config -q` : une variable
obligatoire absente du `.env` (`${X:?X manquant}` dans la pile) ou une
surcharge mal formée arrête le script avant qu'il ait tiré la moindre
image, avec le nom de la variable — et non au milieu d'un `up` qui
laisserait la pile à moitié remplacée. Il tire ensuite les images, puis
`docker compose up --wait` remplace les conteneurs. **Le backend est indisponible le temps des migrations** : le
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
de 4 Go : la plateforme reste sous 3 Go, sauvegardes comprises ; la
supervision, quand elle est activée, ajoute 640 Mo de plafond — 8 Go sont
alors plus confortables ; `GUNICORN_WORKERS` et `GUNICORN_THREADS` dans
`.env` se règlent d'après le nombre de cœurs (voir `.env.example`).

`deploy.sh` lit aussi `SUPERVISION` dans `.env` et en déduit le profil
Compose (« Supervision », plus bas) ; il signale, sans bloquer, un
`.env` sans copie hors machine des sauvegardes (`SAUVEGARDE_DISTANT_ENDPOINT`
vide).

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

Le fichier accepte aussi, pour un environnement jetable seulement,
`totp_secret` (voir plus bas) ; et `manage.py seed_demo --base-jetable` remplit dossiers,
lignes et pièces de démonstration — c'est ce que fait la CI pour ses
captures. Ni l'un ni l'autre sur un serveur réel.

Le back-office Django (`/admin/`) n'est monté qu'en développement (décision 44) et n'est de toute façon pas joignable depuis l'extérieur :
Caddy n'envoie à nginx que ce qui n'est pas `/grafana/`, et nginx ne relaie
à Django que `/api/` — `https://<domaine>/admin/` affiche l'application,
pas le back-office. Il reste accessible depuis le serveur, soumis aux mêmes
verrous que l'API (mot de passe provisoire, double authentification si elle
est exigée), et n'est pas une voie de secours : voir « Réinitialiser un
enrôlement ».

Chaque compte porte une adresse en `ALLOWED_EMAIL_DOMAINS`
(`innovpharma.net`), un mot de passe provisoire, et peut activer la double
authentification depuis le menu de son compte — ou doit le faire à sa
première connexion si `DJANGO_TOTP_REQUIRED=1` (voir plus bas). Seules la
Côte d'Ivoire et le Togo existent au départ ; les quinze autres filiales se
créent depuis l'écran des pays, parmi les codes de `backend/core/africa.py`.

Vérifiez ensuite la copie hors machine des sauvegardes, **avant d'ouvrir
la plateforme aux pays** — c'est la condition de la mise en production :

```bash
docker compose -f docker-compose.prod.yml run --rm sauvegarde --une-fois
docker compose -f docker-compose.prod.yml run --rm sauvegarde-distante --une-fois
./restaurer.sh --lister        # le dump doit apparaître sous « Copie hors machine »
```

Si la supervision est activée (`SUPERVISION=1`), vérifiez-la aussi :
`https://<domaine>/grafana/` demande le compte `GRAFANA_ADMIN_USER` /
`GRAFANA_ADMIN_PASSWORD`, et le tableau de bord « JUSTI INNOV —
supervision » doit montrer ses quatre cibles « en ligne ». Une cible
`backend` « hors ligne » alors que l'API répond signifie presque toujours
un `METRICS_TOKEN` vide ou différent entre `.env` et le conteneur (relancez
la pile après l'avoir changé). Créez alors les comptes « direction » et
« technique » (« Supervision », plus bas).

## Double authentification

Elle est **facultative par défaut** : la direction a reporté son
obligation, le code reste prêt. Chacun l'active depuis le menu de son
compte (« Activer la double authentification »), et un compte enrôlé
présente son code à chaque connexion — le champ « Code » de l'écran de
connexion est là pour lui, facultatif pour les autres. Recommandez-la à qui
contrôle ou justifie.

Pour l'imposer à tous, posez `DJANGO_TOTP_REQUIRED=1` dans `.env` et
relancez la pile : la plateforme reste alors fermée à tout compte non
enrôlé jusqu'à son premier code, comme pour un mot de passe provisoire,
et `GET /api/me/` l'annonce (`totp_required`). Prévenez les comptes avant :
chacun devra avoir une application d'authentification sous la main à sa
connexion suivante.

### Réinitialiser un enrôlement

Un titulaire enrôlé qui a perdu son téléphone ou son application ne peut
plus se connecter, et personne ne peut lui « donner » un code : le secret
n'a été remis qu'à lui.

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

Les administrateurs enrôlés ne sont pas exemptés. Prévoyez donc **deux
comptes `super_admin`** au moins, pour que l'un puisse réinitialiser
l'autre. Le back-office Django n'est pas une voie de secours : il n'est pas
exposé et applique les mêmes verrous que l'API. Si le **dernier**
`super_admin` enrôlé a perdu son téléphone, la seule voie est le shell sur
le serveur, qui fait exactement ce que fait `reset-2fa` — secret effacé,
compteur anti-rejeu remis à zéro, jeton révoqué, entrée `totp_reset` dans
`ChangeLog` — à ceci près que l'entrée ne porte ni auteur ni adresse (il
n'y a pas de requête) : notez qui l'a faite, et pourquoi, dans le journal
d'exploitation.

```bash
cd ~/justi-innov
docker compose -f docker-compose.prod.yml exec -T backend python manage.py shell -c '
from django.contrib.auth.models import User
from accounts.authentication import revoquer_jeton
from accounts.journal import journaliser_compte
from core.models import ChangeLog
u = User.objects.get(username="<nom du compte>")
p = u.profile
etait = p.totp_confirmed
p.totp_secret = ""; p.totp_confirmed_at = None; p.totp_last_counter = None
p.save(update_fields=["totp_secret", "totp_confirmed_at", "totp_last_counter", "updated_at"])
revoquer_jeton(u)
journaliser_compte(None, u, ChangeLog.Actions.TOTP_RESET, changed_fields=["totp"], diff={"totp_confirmed": [etait, False]})
print(u.username, ": double authentification réinitialisée, jeton révoqué")
'
```

Le titulaire refait l'enrôlement à sa prochaine connexion. Vérifiez
l'identité par un autre canal avant, comme pour toute réinitialisation.

Le fichier de `seed_users` accepte une clé `totp_secret` qui enrôle et
confirme le compte d'emblée : elle sert aux environnements jetables (CI,
démonstration) et **ne doit jamais figurer dans le fichier d'un serveur
réel** — un secret qui a transité par un fichier n'est plus un secret.

## Revenir en arrière

**Automatiquement** : si la nouvelle pile ne devient pas saine dans les
240 s, `deploy.sh` relance la pile avec l'étiquette lue dans `.deployed`,
puis sort en erreur — la livraison échoue, la plateforme reste en ligne sur
la version précédente. Le journal du workflow montre l'état de la pile
(`compose ps -a`) et les 100 dernières lignes de **chaque service qui n'est
pas sain** — pas seulement du backend : un Grafana sans mot de passe, un
Caddy sans domaine ou un Prometheus sans jeton bloquent `--wait` tout
autant. S'il n'y a pas d'étiquette précédente (première
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

## Surcharge locale

Une particularité du serveur qui n'a pas sa place dans le dépôt — base
hébergée hors de la pile (`DATA_SOURCE_NAME` pour `postgres-exporter`), un
`GF_SMTP_*` pour les alertes Grafana, un port SMTP local — se pose dans un
`docker-compose.override.yml` à côté de la pile, jamais versionné, déclaré
dans `.env` :

```
COMPOSE_FILE=docker-compose.prod.yml:docker-compose.override.yml
```

`deploy.sh` et `restaurer.sh` lisent cette variable et, si elle est
définie, laissent Compose choisir ses fichiers au lieu d'imposer
`-f docker-compose.prod.yml` (qui la ferait taire) ; `docker compose`
lancé sans `-f` dans ce dossier fait de même. Listez toujours
`docker-compose.prod.yml` en premier. Sans la variable, rien ne change.

## Secrets et variables

Aucun service ne lit `.env` en bloc : `docker-compose.prod.yml` nomme, sous
`environment`, ce que chaque service reçoit, et rien d'autre. Le mot de
passe de Grafana ne va qu'à Grafana, l'adresse ACME qu'à Caddy, la clé
Django qu'au backend et à l'ordonnanceur, les sauvegardes ne voient que la
base ou le stockage. Une variable absente de ces listes n'atteint pas le
conteneur, même posée dans `.env` — pour en ajouter une, c'est la pile
qu'on modifie, pas le `.env`.

Trois valeurs ne passent même pas par l'environnement, mais par des
**secrets Compose** — un fichier sous `/run/secrets/` du seul service qui
le monte, invisible dans `docker inspect` et dans `/proc/<pid>/environ` :

| Secret | Source dans `.env` | Lu par |
|---|---|---|
| `metrics_token` | `METRICS_TOKEN` | Prometheus (`credentials_file`) |
| `postgres_migration_password` | `POSTGRES_MIGRATION_PASSWORD` | `backend/entrypoint.sh` (`POSTGRES_MIGRATION_PASSWORD_FILE`), pour `migrate` et `createcachetable` seulement |
| `sauvegarde_distant_secret` | `SAUVEGARDE_DISTANT_SECRET` | `sauvegarder.sh distant` (service `sauvegarde-distante`), transmis à rclone par l'environnement de ce seul conteneur |

Tant que `creer_role_applicatif.sql` n'a pas été joué, le second est vide
et l'entrypoint ne s'en sert pas. Deux variables sont lues par Compose
lui-même, pas par un service : `COMPOSE_FILE` (« Surcharge locale ») et
`COMPOSE_PROFILES` (« Supervision »). Pour vérifier qu'un secret ne fuit
pas dans un autre service :

```bash
docker compose -f docker-compose.prod.yml config | grep -n GRAFANA_ADMIN_PASSWORD
# une seule ligne attendue, sous grafana
```

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

`POSTGRES_MIGRATION_PASSWORD` n'entre pas dans l'environnement du backend :
il devient le secret Compose `postgres_migration_password`, que
l'entrypoint lit dans un fichier (« Secrets et variables »).

et `docker compose -f docker-compose.prod.yml up -d --wait` relance la
pile. Le script est idempotent : le rejouer renouvelle le mot de passe et
les droits, ce que `restaurer.sh` fait de lui-même après une restauration.
Avec une base désignée par `DATABASE_URL`, `DATABASE_MIGRATION_URL` tient le
rôle de `POSTGRES_MIGRATION_USER`.

## Sauvegardes et restauration

Trois services de la pile s'en chargent chaque nuit, dans le volume
`sauvegardes` puis hors de la machine :

| Service | Quand (UTC) | Quoi |
|---|---|---|
| `sauvegarde` | `SAUVEGARDE_HEURE`, 02:00 | `pg_dump -Fc` de la base dans `base/<base>-<horodatage>.dump` ; les dumps quotidiens de plus de `SAUVEGARDE_RETENTION_JOURS` (30) jours sont supprimés ; le premier dump réussi de chaque mois est copié dans `base/mensuel/<base>-<AAAA-MM>.dump` et **n'est jamais supprimé** |
| `sauvegarde-pieces` | `SAUVEGARDE_PIECES_HEURE`, 02:15 | miroir du bucket des justificatifs dans `pieces/` (`mc mirror --overwrite`, sans suppression : un objet effacé du bucket reste dans la copie) |
| `sauvegarde-distante` | dans la minute qui suit chaque sauvegarde réussie | copie de `base/`, `base/mensuel/` et `pieces/` vers le stockage objet `SAUVEGARDE_DISTANT_*` (`rclone copy`, incrémental), vérification (`rclone check`), journal « ✔ copie distante » ou « ✘ » (« Copie hors machine », ci-dessous) |

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

Les trois tournent avec `sauvegarder.sh`, qui journalise chaque passage
(`docker compose -f docker-compose.prod.yml logs sauvegarde
sauvegarde-pieces sauvegarde-distante`). Une sauvegarde immédiate, avant
une opération risquée :

```bash
docker compose -f docker-compose.prod.yml run --rm sauvegarde --une-fois
docker compose -f docker-compose.prod.yml run --rm sauvegarde-pieces --une-fois
docker compose -f docker-compose.prod.yml run --rm sauvegarde-distante --une-fois
./restaurer.sh --lister
```

### Copie hors machine

**Le volume est sur la même machine que la base.** Une sauvegarde qui brûle
avec le serveur n'en est pas une ; c'est pourquoi **la copie hors machine
est obligatoire avant toute mise en production** (décision 36 de
`docs/model-de-donnees.md`). Une préproduction peut s'en passer ; la
production, non — et rien ne remplace cette copie, ni un instantané du
disque chez le même hébergeur, ni un `rsync` que quelqu'un lance à la main.

Le service `sauvegarde-distante` (image `rclone/rclone`, étiquette
épinglée) la fait à chaque sauvegarde réussie : `sauvegarde` et
`sauvegarde-pieces` déposent une demande dans le volume (`.distant/`), il
la lit dans la minute, envoie ce qui manque au distant, vérifie que chaque
fichier local y est à l'identique — `rclone check`, sur la somme MD5 pour
les dumps (`--checksum` : une copie distante altérée est renvoyée, pas
seulement signalée), sur la taille pour les pièces, dont chaque transfert
est déjà vérifié à l'envoi — et écrit dans son journal :

```
✔ copie distante (base) : 30 dump(s) quotidien(s) et 8 mensuel(s) présents et vérifiés sur distant:sauvegardes-justi/prod
✔ copie distante (pièces) : 1 284 fichier(s) présents et vérifiés sur distant:sauvegardes-justi/prod/pieces
```

ou `✘ copie distante (…)` avec la raison ; la demande reste alors en place
et est retentée un quart d'heure plus tard, jusqu'à réussir. **Un « ✘ » qui
dure est un incident.** Sans `SAUVEGARDE_DISTANT_ENDPOINT`, rien ne part :
le service tourne quand même et le dit, au démarrage et à chaque sauvegarde
(`✘ copie distante non faite : SAUVEGARDE_DISTANT_ENDPOINT vide`), comme
`sauvegarde`, `sauvegarde-pieces`, `deploy.sh` et `restaurer.sh --lister`.

Le distant est un bucket S3 compatible (AWS, Scaleway, OVH, Backblaze,
Infomaniak, un MinIO ailleurs…), **chez un autre hébergeur ou dans une
autre région** que le serveur, avec un compte qui ne peut que lire, écrire
et lister ce bucket — pas le supprimer. Il est disposé ainsi ; les
quotidiens y suivent la même rotation que sur la machine
(`SAUVEGARDE_RETENTION_JOURS`, préfixe `quotidien/` seulement), les
mensuels et les pièces n'y sont jamais supprimés :

```
<bucket>[/<sous-dossier>]/quotidien/<base>-<horodatage>.dump
<bucket>[/<sous-dossier>]/mensuel/<base>-<AAAA-MM>.dump
<bucket>[/<sous-dossier>]/pieces/…
```

| Variable | Rôle |
|---|---|
| `SAUVEGARDE_DISTANT_ENDPOINT` | URL S3 du distant (`https://s3.fr-par.scw.cloud`, `https://s3.eu-west-3.amazonaws.com`…) ; **vide = pas de copie hors machine** |
| `SAUVEGARDE_DISTANT_BUCKET` | bucket, ou `bucket/sous-dossier` ; créé par rclone s'il n'existe pas et que le compte en a le droit |
| `SAUVEGARDE_DISTANT_CLE`, `SAUVEGARDE_DISTANT_SECRET` | le compte ; le secret passe par un secret Compose, pas par l'environnement (« Secrets et variables ») |
| `SAUVEGARDE_DISTANT_REGION` | si le fournisseur l'exige (`eu-west-3`, `fr-par`) ; vide pour MinIO ou OVH |
| `SAUVEGARDE_DISTANT_FOURNISSEUR` | nom du fournisseur au sens de rclone (`Other` par défaut ; `AWS`, `Scaleway`, `Wasabi`…) |

Après avoir renseigné ces variables, `deploy.sh` (ou `docker compose up -d
sauvegarde-distante`) recrée le service ; vérifiez sans attendre la nuit :

```bash
docker compose -f docker-compose.prod.yml run --rm sauvegarde-distante --une-fois
./restaurer.sh --lister        # section « Copie hors machine »
```

Le service envoie deux fichiers à la fois, par morceaux de 8 Mo
(`mem_limit: 128m`) ; chaque réglage rclone se surcharge par la variable du
même nom (`RCLONE_TRANSFERS`, `RCLONE_BWLIMIT`…) dans un
`docker-compose.override.yml` (« Surcharge locale »). Les dumps quotidiens
partent tous les jours entiers ; les pièces, seulement ce qui a changé.

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

### Restaurer depuis la copie hors machine

Quand le serveur est perdu — ou son volume `sauvegardes` — la restauration
part du distant. Sur le serveur reconstruit (« Préparer un serveur »,
`deploy.sh` : la pile est en ligne, vide), avec le même `.env`, donc les
mêmes `SAUVEGARDE_DISTANT_*` :

1. Lister ce que le distant contient et choisir la nuit à restaurer :
   ```bash
   ./restaurer.sh --lister
   ```
2. Rapatrier le dump dans le volume et restaurer la base — `--depuis-distant`
   fait les deux ; rclone vérifie la somme du fichier reçu, un fichier
   absent ou vide est refusé, puis la restauration est celle décrite plus
   haut (confirmation, comptages, rôle applicatif, relance) :
   ```bash
   ./restaurer.sh --depuis-distant justi_innov-2026-09-04T020000Z.dump
   ./restaurer.sh --depuis-distant mensuel/justi_innov-2026-08.dump      # une copie mensuelle
   ./restaurer.sh --depuis-distant <dump> --base test_restauration      # dans une base jetable
   ```
3. Rapatrier le miroir des pièces et le remettre dans le bucket :
   ```bash
   ./restaurer.sh --depuis-distant --pieces
   ```
4. Vérifier, comme au test trimestriel : comptages, dernière entrée du
   journal d'audit, et une dépense justifiée prise au hasard dont la pièce
   s'ouvre.

Faites ce chemin complet **une fois avant la mise en production**, sur un
serveur jetable : c'est la seule preuve que la copie hors machine se
restaure, et que le compte du distant a bien les droits de lecture.

Avec une base hébergée hors de la pile (`DATABASE_URL`), `sauvegarder.sh`
la sauvegarde bien — `pg_dump` accepte l'URL — mais `restaurer.sh` ne
connaît que le Postgres de la pile : restaurez alors avec `pg_restore` et
la même URL, depuis le conteneur `sauvegarde`.

### Test de restauration trimestriel

Une sauvegarde qu'on n'a jamais restaurée n'est qu'un espoir. Chaque
trimestre, sur le serveur, dans une base jetable — la pile reste en ligne,
rien n'est arrêté :

1. Vérifier que les sauvegardes récentes existent, ont une taille
   plausible (un dump qui pèse quelques kilo-octets est vide) et sont bien
   sur le distant — même nom, même taille dans les deux listes, et un
   « ✔ copie distante » chaque nuit dans le journal :
   ```bash
   ./restaurer.sh --lister
   docker compose -f docker-compose.prod.yml logs --since 72h sauvegarde sauvegarde-pieces sauvegarde-distante
   ```
2. Restaurer le dernier dump dans une base jetable — un trimestre sur
   deux, depuis le distant plutôt que depuis le volume, pour prouver que la
   copie hors machine se restaure :
   ```bash
   ./restaurer.sh justi_innov-<horodatage>.dump --base test_restauration
   ./restaurer.sh --depuis-distant justi_innov-<horodatage>.dump --base test_restauration
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
atteignable, par Caddy, sur `https://<domaine>/grafana/`, derrière ses
propres comptes — distincts de ceux de l'application. Les administrateurs
de l'application y arrivent par l'entrée « Supervision » du menu de leur
compte, qui ouvre `/grafana/` dans un nouvel onglet.

### Un profil Compose optionnel

La supervision est un **profil Compose, `supervision`, désactivé par
défaut** (décision 37 de `docs/model-de-donnees.md`) : l'exploitation
l'active quand elle en a besoin, et une machine de 4 Go n'en porte pas le
poids (640 Mo de plafond mémoire) tant qu'elle ne l'a pas demandé. Un seul
drapeau dans `.env` commande tout :

```
SUPERVISION=1
COMPOSE_PROFILES=supervision
```

| Effet de `SUPERVISION=1` | Par qui |
|---|---|
| `prometheus`, `postgres-exporter`, `node-exporter`, `grafana` font partie de la pile (`profiles: ["supervision"]`) | `deploy.sh` et `restaurer.sh` exportent `COMPOSE_PROFILES=supervision` d'après `SUPERVISION` ; `docker compose` lancé à la main lit `COMPOSE_PROFILES` dans `.env`, d'où la seconde ligne — `deploy.sh` signale un `.env` où les deux se contredisent |
| Caddy route `/grafana/` vers Grafana | `docker-compose.prod.yml` transmet `SUPERVISION` à Caddy ; le Caddyfile n'a pas de bloc conditionnel, la variable est substituée dans une expression constante (`"1" == "1"`) avant l'analyse, et le fichier valide dans les deux cas — sans supervision, `/grafana/` répond 404 avec une phrase, pas la page d'accueil de l'application ni un 502 |
| L'interface montre l'entrée « Supervision » | le backend reçoit `SUPERVISION` (`x-django`) et renvoie le drapeau `supervision` sur `/api/configuration/` ; l'interface ne l'affiche que s'il est vrai |

`METRICS_TOKEN` et `GRAFANA_ADMIN_PASSWORD` ne servent que si le profil
est actif, mais Compose interpole toute la pile avant d'appliquer les
profils : `GRAFANA_ADMIN_PASSWORD` doit être renseigné dans `.env` dans
tous les cas (`deploy.sh` le dit sinon), plutôt que d'accepter un vide qui
laisserait Grafana démarrer un jour avec son mot de passe par défaut.
Pour l'activer sur une pile en ligne : les deux lignes dans
`.env`, puis `deploy.sh` rejoué avec l'étiquette en cours (ou `docker
compose up -d --wait`) — Caddy et le backend sont recréés avec le
drapeau. Pour la désactiver : `SUPERVISION=0`, retirer `COMPOSE_PROFILES`,
rejouer `deploy.sh`, qui arrête les quatre services (Compose ne tient pas
pour orphelins les conteneurs d'un profil inactif) en gardant leurs
volumes — `prometheus_data` et `grafana_data` attendent la prochaine
activation.

Vérifier la pile vue par Compose dans chaque cas :

```bash
docker compose -f docker-compose.prod.yml config --services                              # sans
COMPOSE_PROFILES=supervision docker compose -f docker-compose.prod.yml config --services # avec
```

### Comptes Grafana

Grafana est partagé avec la direction et l'équipe technique. Trois comptes,
pas plus : l'administrateur (`GRAFANA_ADMIN_USER` /
`GRAFANA_ADMIN_PASSWORD`, réservé à l'exploitation), **« direction »** en
lecture seule et **« technique »** en édition. `docker-compose.prod.yml`
règle ce qui rend le partage sûr et confortable :

| Variable | Effet |
|---|---|
| `GF_USERS_VIEWERS_CAN_EDIT=false` | un Viewer ne modifie rien, pas même « pour voir » : la direction lit |
| `GF_USERS_EDITORS_CAN_ADMIN=false` | un Editor ne gère ni comptes ni organisation |
| `GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH` | le tableau de bord « JUSTI INNOV — supervision » est la page d'accueil de chacun |
| `GF_USERS_DEFAULT_THEME=light` | thème clair par défaut, comme l'application ; chacun change le sien |
| `GF_USERS_DEFAULT_LANGUAGE=fr-FR` | interface en français par défaut, comme l'application ; chacun change la sienne |
| `GF_USERS_ALLOW_SIGN_UP=false`, `GF_AUTH_ANONYMOUS_ENABLED=false` | pas d'inscription, pas d'accès anonyme |

Les deux comptes se créent une fois, depuis l'administrateur — dans
Grafana (Administration › Users and access › Users › New user, puis le rôle
dans l'organisation) ou par l'API, depuis n'importe quel poste :

```bash
GRAFANA=https://<domaine>/grafana
AUTH="$GRAFANA_ADMIN_USER:$GRAFANA_ADMIN_PASSWORD"
# Un nouveau compte reçoit le rôle Viewer (GF_USERS_AUTO_ASSIGN_ORG_ROLE) :
# « direction » n'a rien de plus à régler.
curl -fsS -u "$AUTH" -H 'Content-Type: application/json' \
    -X POST "$GRAFANA/api/admin/users" \
    -d '{"name":"Direction","login":"direction","password":"<mot de passe 1>"}'
curl -fsS -u "$AUTH" -H 'Content-Type: application/json' \
    -X POST "$GRAFANA/api/admin/users" \
    -d '{"name":"Équipe technique","login":"technique","password":"<mot de passe 2>"}'
# « technique » passe Editor ; l'identifiant est celui renvoyé ("id") par la
# création, ou se lit dans GET /api/org/users.
curl -fsS -u "$AUTH" -H 'Content-Type: application/json' \
    -X PATCH "$GRAFANA/api/org/users/<id de technique>" -d '{"role":"Editor"}'
```

Remettez chaque mot de passe par un autre canal que l'e-mail, et
changez-le si la personne change : ce sont des comptes de fonction, pas de
personne. Un Viewer voit les mesures d'exploitation, jamais une donnée
métier (voir plus bas) ; un Editor peut composer d'autres tableaux de bord
et poser des alertes, mais le tableau de bord de la plateforme vient du
dépôt et reste en lecture seule pour tous.

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
n'est pas joignable depuis l'extérieur. Le nom `backend`, sous lequel
Prometheus l'interroge, est ajouté à `ALLOWED_HOSTS` par
`backend/config/settings.py` — `DJANGO_ALLOWED_HOSTS` ne porte que le
domaine public. Prometheus est servi sous `/grafana/` par Caddy, qui
transmet le préfixe tel quel : Grafana le sert lui-même
(`GF_SERVER_SERVE_FROM_SUB_PATH`) ; retirer le préfixe le faisait boucler
sur sa page de connexion.

Le tableau de bord « JUSTI INNOV — supervision » (`uid` `justi-innov`) est
en lecture seule dans Grafana : il vient du dépôt. Pour le modifier, faites
la modification dans Grafana, exportez le JSON (Share › Export) et
remplacez `grafana/dashboards/justi-innov.json` ; la livraison suivante — ou
un `deploy.sh` rejoué — le recharge. Il montre :

- l'état des cibles de collecte (`up`) : un backend « hors ligne » alors
  que l'API répond est un problème de jeton (`METRICS_TOKEN` vide ou
  différent entre `.env` et le conteneur) ;
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

Vérifier la configuration sans lancer la pile. `promtool` vérifie que le
fichier du jeton existe : hors de la pile, on lui en monte un factice.

```bash
echo factice > /tmp/jeton-factice
docker run --rm -v "$PWD/prometheus/prometheus.yml:/p.yml:ro" \
    -v /tmp/jeton-factice:/run/secrets/metrics_token:ro \
    --entrypoint promtool prom/prometheus:v2.53.5 check config /p.yml
docker run --rm -e APP_DOMAIN=exemple.org -e ACME_EMAIL=a@exemple.org \
    -e SUPERVISION=1 \
    -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2.8-alpine \
    caddy validate --config /etc/caddy/Caddyfile                # et avec SUPERVISION=0
docker compose -f docker-compose.prod.yml config >/dev/null   # avec le .env
```

Recharger Prometheus après avoir modifié `prometheus/prometheus.yml`, sans
le redémarrer : par un signal, et non par le point `/-/reload`, qui n'est
pas ouvert (`--web.enable-lifecycle` exposerait sans authentification un
arrêt et un rechargement à quiconque joint le réseau interne).

```bash
docker compose -f docker-compose.prod.yml kill -s HUP prometheus
docker compose -f docker-compose.prod.yml logs --tail 5 prometheus   # « Completed loading of configuration file »
```
