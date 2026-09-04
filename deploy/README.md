# Déploiement

La livraison continue (`.github/workflows/cd.yml`) livre `main` en
préproduction et les tags `v*` en production, après approbation. Ce dossier
contient ce qu'elle pose sur le serveur.

```
main ──────▶ CI ──▶ images ghcr.io ──▶ staging      (automatique)
tag v1.2.3 ▶ CI ──▶ images ghcr.io ──▶ production   (approbation requise)
```

| Fichier | Rôle |
|---|---|
| `docker-compose.prod.yml` | la pile : Postgres, MinIO, backend, ordonnanceur, frontend, Caddy, sauvegardes |
| `Caddyfile` | entrée publique, TLS automatique |
| `deploy.sh` | tire une étiquette d'images, relance la pile, attend qu'elle soit saine |
| `.env.example` | modèle du `.env` du serveur, jamais versionné |
| `creer_role_applicatif.sql` | rôle Postgres du service, sans droit de modifier le schéma |
| `sauvegarder.sh` | sauvegarde nocturne de la base et des justificatifs, dans le volume `sauvegardes` |
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
   en `chmod 600`.
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
de 4 Go ; `GUNICORN_WORKERS` et `GUNICORN_THREADS` dans `.env` se règlent
d'après le nombre de cœurs (voir `.env.example`).

## Première mise en service

Une fois la pile en ligne, les comptes se créent depuis le serveur, à partir
d'un fichier qui ne quitte jamais la machine :

```bash
cd ~/justi-innov
docker compose -f docker-compose.prod.yml cp seed_users.json backend:/tmp/seed.json
docker compose -f docker-compose.prod.yml exec backend \
    python manage.py seed_users --file /tmp/seed.json
```

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
| `sauvegarde` | `SAUVEGARDE_HEURE`, 02:00 | `pg_dump -Fc` de la base dans `base/<base>-<horodatage>.dump` ; les dumps de plus de `SAUVEGARDE_RETENTION_JOURS` (14) jours sont supprimés |
| `sauvegarde-pieces` | `SAUVEGARDE_PIECES_HEURE`, 02:15 | miroir du bucket des justificatifs dans `pieces/` (`mc mirror --overwrite`, sans suppression : un objet effacé du bucket reste dans la copie) |

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
