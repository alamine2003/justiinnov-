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
| `docker-compose.prod.yml` | la pile : Postgres, MinIO, backend, ordonnanceur, frontend, Caddy |
| `Caddyfile` | entrée publique, TLS automatique |
| `deploy.sh` | tire une étiquette d'images, relance la pile, attend qu'elle soit saine |
| `.env.example` | modèle du `.env` du serveur, jamais versionné |

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

## Sauvegardes

La pile ne les fait pas à votre place. Au minimum, chaque nuit :

```bash
docker compose -f docker-compose.prod.yml exec -T db \
    pg_dump -U justi justi_innov | gzip > "sauvegarde-$(date +%F).sql.gz"
```

et une copie du volume `miniodata`, qui contient les justificatifs — la
preuve, c'est-à-dire la raison d'être de la plateforme.
