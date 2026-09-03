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
   | secret | `DEPLOY_KNOWN_HOSTS` | sortie de `ssh-keyscan -H <hôte>` (recommandé) |
   | variable | `APP_DOMAIN` | domaine public |
   | variable | `DEPLOY_PATH` | `~/justi-innov` par défaut |

   Sur `production`, ajoutez des relecteurs obligatoires : c'est là, et pas
   dans le workflow, que se règle l'approbation.

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

Chaque déploiement écrit l'étiquette livrée dans `.deployed`. Pour revenir à
la précédente, relancez `deploy.sh` avec elle — l'image est encore sur le
serveur et sur le registre :

```bash
IMAGE_TAG=sha-… BACKEND_IMAGE=ghcr.io/<org>/<dépôt>-backend \
FRONTEND_IMAGE=ghcr.io/<org>/<dépôt>-frontend ./deploy.sh
```

Les migrations ne se défont pas seules : ne revenez pas en deçà d'une version
dont la migration a supprimé une colonne.

## Sauvegardes

La pile ne les fait pas à votre place. Au minimum, chaque nuit :

```bash
docker compose -f docker-compose.prod.yml exec -T db \
    pg_dump -U justi justi_innov | gzip > "sauvegarde-$(date +%F).sql.gz"
```

et une copie du volume `miniodata`, qui contient les justificatifs — la
preuve, c'est-à-dire la raison d'être de la plateforme.
