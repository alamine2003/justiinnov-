# Déploiement de JUSTI INNOV

> La plateforme tourne sur ce type de serveur (Hetzner, domaine gratuit
> `178-105-215-49.sslip.io`). La livraison par SSH de `cd.yml` ne part que
> si la variable de dépôt `DEPLOIEMENT_SSH` vaut `1` (posée). Railway reste
> une voie de repli, décrite dans
> [`docs/deploiement-railway.md`](../docs/deploiement-railway.md).

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
| `preparer_serveur.sh` | prépare une machine Ubuntu neuve (« Préparer un serveur », plus bas) |
| `deploy.sh` | vérifie la configuration (`compose config`), tire une étiquette d'images, relance la pile, attend qu'elle soit saine ; sinon montre l'état et les journaux de chaque service non sain et rétablit l'étiquette précédente. Une livraison réussie réinscrit étiquette et noms d'images dans le `.env`, pour que les commandes ci-dessous marchent ensuite telles quelles |
| `.env.example` | modèle du `.env` du serveur, jamais versionné ; aucun service ne le lit en bloc (« Secrets et variables », plus bas) |
| `docker-compose.override.yml` | facultatif, jamais versionné : surcharge locale déclarée par `COMPOSE_FILE` dans `.env` (« Surcharge locale ») |
| `creer_role_applicatif.sql` | rôle Postgres du service, sans droit de modifier le schéma |
| `sauvegarder.sh` | sauvegarde nocturne de la base (30 jours de quotidiens, copie mensuelle conservée sans limite) et des justificatifs, dans le volume `sauvegardes`, puis copie hors machine de chaque sauvegarde réussie vers un stockage objet S3 (`rclone`), vérifiée |
| `restaurer.sh` | restaure un dump dans la pile ou dans une base jetable, et remet les justificatifs — depuis le volume, ou depuis la copie hors machine (`--depuis-distant`) |

## Préparer un serveur

1. Une machine Linux avec Docker Engine et le plugin Compose (v2.24 ou plus),
   les ports 80 et 443 ouverts, un enregistrement DNS vers elle. Le serveur
   tire ses images de trois registres, tous en sortie HTTPS : `ghcr.io`
   (backend et frontend, avec le jeton de livraison), Docker Hub (Postgres,
   Caddy, les exporteurs) et `quay.io` (MinIO et son client `mc` — le
   registre de l'éditeur, sans limite de téléchargement anonyme, là où
   Docker Hub refuse cette image aux runners de la CI).
2. Un compte de livraison `deploy` **sans le groupe `docker`** (ce groupe
   vaut root), dont la clé SSH ne peut exécuter qu'une commande forcée,
   `justi-livrer` (« Réduire les pouvoirs de la livraison », plus bas), et
   un répertoire d'exploitation `/home/deploy/justi-innov` **propriété de
   root**. Sur une Ubuntu neuve, `preparer_serveur.sh` fait tout cela d'un
   coup — Docker et Compose, le compte, la commande forcée et son sudo, le
   pare-feu limité à 22, 80 et 443, les mises à jour de sécurité
   automatiques, SSH par clé seulement — et se relance sans dégât. Les
   fichiers d'exploitation partent d'abord, en root :
   ```bash
   ssh-keygen -t ed25519 -N "" -C deploy@justi-innov -f ~/.ssh/justi-innov-deploy
   rsync -a --exclude .env deploy/ root@<hôte>:/home/deploy/justi-innov/
   ssh root@<hôte> "bash -s -- '$(cat ~/.ssh/justi-innov-deploy.pub)'" < deploy/preparer_serveur.sh
   ```
   Les humains entrent en **root**, avec la clé que l'hébergeur y a posée ;
   toute l'exploitation (`docker compose`, `restaurer.sh`, `.env`) se fait
   en root, dans `/home/deploy/justi-innov`.
3. Le fichier `.env` dans `/home/deploy/justi-innov/`, d'après `.env.example`,
   `root:root` et `chmod 600`. Quatre secrets s'y génèrent, avec
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
   dans `SAUVEGARDE_DISTANT_*`, **et une clé de chiffrement**
   (`SAUVEGARDE_CHIFFREMENT_CLE`, gardée aussi hors du serveur) : un bucket
   S3 compatible chez un autre hébergeur ou dans une autre région, avec un
   compte qui ne peut que lire, écrire et lister ce bucket — pas supprimer.
   C'est **obligatoire avant toute mise en production** (« Copie hors
   machine », plus bas) ; une préproduction peut s'en passer, `deploy.sh`
   et les services de sauvegarde le rappellent alors à chaque occasion.
5. Dans GitHub, un environnement `staging` et un environnement `production`
   (Settings › Environments) portant chacun :

   | Type | Nom | Contenu |
   |---|---|---|
   | secret | `DEPLOY_HOST` | hôte SSH |
   | secret | `DEPLOY_USER` | `deploy` |
   | secret | `DEPLOY_SSH_KEY` | clé privée correspondante |
   | secret | `DEPLOY_KNOWN_HOSTS` | sortie de `ssh-keyscan -H <hôte>`, **obligatoire** : le workflow refuse de partir sans, plutôt que d'accepter l'empreinte de n'importe quelle machine au premier contact |
   | variable | `APP_DOMAIN` | domaine public |

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
   compte du registre) sont vérifiées par expression régulière avant
   l'appel SSH, puis **revérifiées sur le serveur** par la commande forcée
   de la clé, avec les mêmes motifs ; le jeton de registre, lui, ne transite
   que par l'entrée standard. Étiquette et noms d'images sont ensuite
   réinscrits dans le `.env` par `deploy.sh` (« Commandes d'exploitation »,
   plus bas). La livraison ne copie aucun fichier sur le serveur.

   Sur le dépôt (Settings › Branches), une **règle de protection de
   `main`** : *Require a pull request before merging*, *Require status
   checks to pass* avec les cinq travaux d'`Intégration continue`, *Do not
   allow bypassing the above settings*. Sans elle, une poussée directe sur
   `main` part en préproduction sans relecture ; avec elle, rien n'entre
   dans `main` qu'une pull request verte.

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
même étiquette recharge la configuration du répertoire d'exploitation
(Caddyfile, Prometheus, tableaux de bord Grafana), puisque ces fichiers
sont montés depuis ce dossier et non copiés dans les images.

## Réduire les pouvoirs de la livraison

La clé SSH de livraison, détenue par GitHub, ne peut faire **qu'une chose**
sur le serveur : demander le déploiement d'une étiquette d'images. Avant
(audit du 8 septembre 2026, §3.4), le compte `deploy` était membre du
groupe `docker` — ce qui vaut root —, et la livraison recopiait tout
`deploy/` depuis le dépôt puis exécutait le `deploy.sh` qu'elle venait
d'écrire : quiconque poussait sur `main` exécutait du code en root sur le
serveur, sans approbation. Désormais :

- `deploy` n'est **pas** dans le groupe `docker` et n'a d'autre droit
  `sudo` que `/usr/local/bin/justi-livrer` (`/etc/sudoers.d/justi-livrer`) ;
- sa clé porte une **commande forcée** (`command="sudo -n
  /usr/local/bin/justi-livrer"`, sans pty, sans transfert de port ni
  d'agent) : sshd ignore la commande demandée et lance celle-ci, qui relit
  la demande dans `SSH_ORIGINAL_COMMAND`, refuse tout ce qui n'est pas
  exactement `livrer <IMAGE_TAG> <BACKEND_IMAGE> <FRONTEND_IMAGE>
  <APP_DOMAIN> <GHCR_USER>` — chaque valeur bornée par les mêmes
  expressions régulières que `cd.yml` — puis lance le `deploy.sh` du
  répertoire d'exploitation ;
- ce répertoire, `deploy.sh`, `docker-compose.prod.yml`, les scripts de
  sauvegarde et le `.env` appartiennent à **root** : la clé ne peut ni les
  lire (le `.env`), ni les remplacer, ni copier quoi que ce soit ;
- la CI ne change donc **jamais** ce qui tourne en root. Les fichiers de
  `deploy/` se mettent à jour à la main, en root, depuis un dépôt à jour —
  après avoir relu ce qui change :
  ```bash
  git -C ~/justiinnov- diff v1.0.3 HEAD -- deploy/        # ce qui va changer
  rsync -a --exclude .env --exclude .deployed deploy/ root@<hôte>:/home/deploy/justi-innov/
  ssh root@<hôte> 'chown -R root:root /home/deploy/justi-innov && chmod 755 /home/deploy/justi-innov/*.sh && install -m 0755 /home/deploy/justi-innov/justi-livrer /usr/local/bin/justi-livrer'
  ```
  puis une livraison (ou `deploy.sh` en root) pour que la pile relise les
  fichiers montés.

**Passer un serveur en service à ce modèle** — l'opération, sa
vérification et son retour arrière :

1. Poser `justi-livrer` et les fichiers de `deploy/` à jour, en root
   (`rsync` ci-dessus), puis :
   ```bash
   ssh root@<hôte> "bash -s -- '$(cat ~/.ssh/justi-innov-deploy.pub)'" < deploy/durcir_livraison.sh
   ```
   Le script retire `deploy` du groupe `docker`, pose le sudo restreint et
   la commande forcée, **remplace** `~deploy/.ssh/authorized_keys` par la
   seule clé de livraison (les clés des humains n'y sont plus : ils entrent
   en root), passe le répertoire à root et le `.env` en 600.
2. Vérifier, depuis le poste, que la clé ne peut rien d'autre :
   ```bash
   ssh -i ~/.ssh/justi-innov-deploy deploy@<hôte> id          # → « livraison refusée : aucune commande »
   ssh -i ~/.ssh/justi-innov-deploy deploy@<hôte> 'livrer x'  # → « forme attendue : … »
   ssh -i ~/.ssh/justi-innov-deploy deploy@<hôte> 'livrer sha-000000000000 ghcr.io/x ghcr.io/y a.b c; id'
   #                                                            → « GHCR_USER invalide » : rien ne s'enchaîne
   ssh root@<hôte> 'id deploy; sudo -l -U deploy'             # sans « docker » ; justi-livrer seul
   ```
   puis une livraison réelle — Actions › Livraison continue › *Run
   workflow* sur `staging`, ou le tag suivant — et, dans le journal du
   travail `Déployer`, la sortie de `deploy.sh` jusqu'à « ✔ … en ligne ».
3. Retour arrière, si la livraison ne passe pas : le serveur n'a rien
   perdu, la pile tourne. Rétablir l'ancien modèle le temps de comprendre :
   ```bash
   ssh root@<hôte> 'usermod -aG docker deploy && rm -f /etc/sudoers.d/justi-livrer \
     && printf "%s\n" "$(cat ~/.ssh/justi-innov-deploy.pub)" > /home/deploy/.ssh/authorized_keys \
     && chown -R deploy:deploy /home/deploy/justi-innov'
   ```
   et `git revert` du commit qui a changé `cd.yml` (la livraison recopie
   alors `deploy/` comme avant). L'un sans l'autre ne marche pas : l'ancien
   `cd.yml` a besoin d'un `deploy` qui écrit dans le répertoire, le nouveau
   d'une commande forcée.

## Commandes d'exploitation

Toutes celles qui suivent passent par `docker compose`, qui a besoin de
`BACKEND_IMAGE`, `FRONTEND_IMAGE` et `IMAGE_TAG` pour interpoler la pile.
La livraison continue les transmet dans `.deploy-env`, effacé aussitôt lu ;
`deploy.sh` les réinscrit donc dans le `.env` à la fin de chaque livraison
réussie, et Compose les y lit de lui-même. Rien à préfixer.

Compose exige en outre que **toute variable nommée par un secret existe**,
même vide : `METRICS_TOKEN`, `POSTGRES_MIGRATION_PASSWORD` et
`SAUVEGARDE_DISTANT_SECRET` sont donc déclarées dans `.env.example`, et
`deploy.sh` exporte à vide celles qui manqueraient. Une seule absente et
Compose refuse de créer le conteneur — « environment variable "…" required
by secret "…" is not set » —, y compris pour une commande d'exploitation sur
une pile parfaitement saine.

Sur un serveur préparé avant ces deux garde-fous, complétez son `.env` une
fois pour toutes :

```bash
cd ~/justi-innov
grep -q '^POSTGRES_MIGRATION_PASSWORD=' .env || echo 'POSTGRES_MIGRATION_PASSWORD=' >> .env
```

puis relivrez, ou ajoutez à la main l'étiquette et les noms d'images lus
dans `.deployed`. En dépannage, `docker exec justi-innov-backend-1 …` et
`docker cp` parlent directement aux conteneurs, sans passer par Compose.

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

## Courrier

Le backend refuse de démarrer sans transport de courrier : `EMAIL_HOST`
renseigné, ou `EMAIL_BACKEND_CONSOLE=1` pour acquitter son absence. **Les
deux ensemble sont refusés** — un hôte de remplissage l'emporterait sur le
drapeau, et chaque envoi échouerait après dix secondes sans que rien
n'atterrisse dans les journaux.

En production, le transport est le SMTP de Gmail, avec un **mot de passe
d'application** (Google refuse un mot de passe de compte depuis la
suppression des « applications moins sécurisées ») :

```
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=<le compte qui envoie>
EMAIL_HOST_PASSWORD=<seize lettres, sans espaces>
EMAIL_USE_TLS=1
DEFAULT_FROM_EMAIL=<le même compte>
```

Trois contraintes à connaître avant d'ouvrir la plateforme aux pays :

- **Gmail réécrit l'expéditeur.** Les messages partent de
  `EMAIL_HOST_USER`, quelle que soit la valeur de `DEFAULT_FROM_EMAIL` :
  seule une adresse vérifiée sur ce compte y échappe. Les deux valeurs sont
  donc gardées identiques.
- **Le mot de passe d'application ouvre aussi l'IMAP** du compte : qui lit
  le `.env` lit le courrier de ce compte. Le compte utilisé doit être
  **dédié à la plateforme**, jamais celui d'une personne.
- **500 messages par jour** pour un compte Gmail ordinaire, 2 000 sur
  Google Workspace. Les alertes et les rapports périodiques restent loin
  du plafond ; un envoi en masse ne passerait pas.

Le jour où le domaine aura ses propres boîtes, seules ces six lignes
changent. Pour vérifier après coup :

```bash
docker compose -f docker-compose.prod.yml exec -T backend python manage.py shell -c "
from django.core.mail import send_mail
from django.conf import settings
send_mail('Test', 'Controle.', settings.DEFAULT_FROM_EMAIL, [settings.DEFAULT_FROM_EMAIL], fail_silently=False)
print('parti')
"
```

Rappel : les notifications vont à l'adresse de chaque compte, qui doit
appartenir à `ALLOWED_EMAIL_DOMAINS`. Si ces boîtes n'existent pas encore
chez le fournisseur du domaine, les messages partiront et rebondiront.

### Remplacer le compte d'envoi

Le compte d'envoi en service depuis le 7 septembre 2026 est un compte
Gmail **personnel**, dont le mot de passe d'application a transité en
clair : **son remplacement est urgent, et sa révocation immédiate après
bascule**. Le nouveau compte est **dédié** — un Gmail créé pour la
plateforme (`justi.innov.notifications@gmail.com` ou équivalent, avec
validation en deux étapes, sans rien d'autre dedans), ou une boîte du
domaine le jour où il en a — et son mot de passe d'application ne sert qu'à
`EMAIL_HOST_PASSWORD`. Bascule testée avant révocation :

1. Créer le compte dédié, activer la validation en deux étapes, générer un
   mot de passe d'application ; le noter dans le gestionnaire de mots de
   passe, jamais dans un chat ni un e-mail.
2. Sur le serveur, en root, remplacer `EMAIL_HOST_USER`,
   `EMAIL_HOST_PASSWORD` et `DEFAULT_FROM_EMAIL` dans `.env` (éditeur, pas
   `sed` : un mot de passe collé avec ses espaces a déjà cassé une
   commande), puis relancer :
   ```bash
   docker compose -f docker-compose.prod.yml up -d --wait backend scheduler
   ```
   (`deploy.sh` exporte les secrets absents du `.env` avant `up` ; à la
   main, exportez-les vides de même : `export METRICS_TOKEN= …`, ou passez
   par `./deploy.sh` avec l'étiquette en ligne.)
3. Envoyer le message de contrôle ci-dessus, **vers une adresse d'un
   compte de la plateforme** : il doit arriver, de la nouvelle adresse.
4. Seulement alors, dans le compte Google personnel : *Sécurité ›
   Validation en deux étapes › Mots de passe des applications* → supprimer
   celui de la plateforme ; puis changer le mot de passe du compte, qui a
   lui aussi transité.
5. Refaire le message de contrôle : il part encore (le nouveau compte ne
   dépend pas de l'ancien). Consigner la date de bascule.

Retour arrière avant l'étape 4 : remettre les trois lignes précédentes du
`.env` et relancer. Après l'étape 4, il n'y a plus de retour : c'est voulu.

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

et `./deploy.sh` avec l'étiquette en ligne (ou `docker compose -f
docker-compose.prod.yml up -d --wait backend scheduler`, après avoir
exporté les secrets absents comme le fait `deploy.sh`) relance la pile.
Le script est idempotent : le rejouer renouvelle le mot de passe et les
droits, ce que `restaurer.sh` fait de lui-même après une restauration.
Avec une base désignée par `DATABASE_URL`, `DATABASE_MIGRATION_URL` tient le
rôle de `POSTGRES_MIGRATION_USER`.

**Vérifier que c'est bien le rôle restreint qui sert** — le fichier `.env`
ne le prouve pas, la base oui :

```bash
docker compose -f docker-compose.prod.yml exec backend python manage.py shell -c \
  "from django.db import connection; c = connection.cursor(); c.execute('SELECT current_user'); print(c.fetchone())"
# → ('justi_app',)
docker compose -f docker-compose.prod.yml exec -T db psql -U justi_app -d justi_innov \
  -c 'CREATE TABLE essai_droits (id int)'
# → ERROR: permission denied for schema public — c'est le résultat attendu
```

Un `CREATE TABLE` qui passe signifie que Django tourne encore avec le
propriétaire : le `.env` n'a pas été relu, ou `POSTGRES_USER` y est resté
`justi`. **Retour arrière** : remettre les quatre variables à leur valeur
précédente et relancer ; le rôle `justi_app` peut rester, il ne gêne pas.

## Sauvegardes et restauration

Trois services de la pile s'en chargent chaque nuit, dans le volume
`sauvegardes` puis hors de la machine :

| Service | Quand (UTC) | Quoi |
|---|---|---|
| `sauvegarde` | `SAUVEGARDE_HEURE`, 02:00 | `pg_dump -Fc` de la base dans `base/<base>-<horodatage>.dump` ; les dumps quotidiens de plus de `SAUVEGARDE_RETENTION_JOURS` (30) jours sont supprimés ; le premier dump réussi de chaque mois est copié dans `base/mensuel/<base>-<AAAA-MM>.dump` et **n'est jamais supprimé** |
| `sauvegarde-pieces` | `SAUVEGARDE_PIECES_HEURE`, 02:15 | miroir du bucket des justificatifs dans `pieces/` (`mc mirror --overwrite`, sans suppression : un objet effacé du bucket reste dans la copie). Lit `AWS_ACCESS_KEY_ID` et `AWS_SECRET_ACCESS_KEY` dans son environnement ; absentes ou vides, le miroir est **refusé** avec « identifiants du stockage objet absents » et sans marqueur de réussite — `verifier_sauvegardes` le signale dès le lendemain |
| `sauvegarde-distante` | dans la minute qui suit chaque sauvegarde réussie | copie **chiffrée** de `base/`, `base/mensuel/` et `pieces/` vers le stockage objet `SAUVEGARDE_DISTANT_*` (`rclone copy` dans un coffre `crypt`, incrémental), vérification (`rclone cryptcheck`), journal « ✔ copie distante » ou « ✘ » (« Copie hors machine », ci-dessous) ; **n'efface rien sur le distant** |

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

**Objectifs, à connaître avant d'ouvrir aux pays.**

| | Objectif | Ce qui le tient |
|---|---|---|
| Perte de données maximale (RPO) | **24 h** : ce qui a été saisi depuis la sauvegarde de 02:00 est perdu si le serveur l'est | une sauvegarde par nuit ; à resserrer à 6 h (`SAUVEGARDE_HEURE` ne prend qu'une heure : dupliquer le service dans une surcharge locale) quand les pays saisissent tous les jours |
| Délai de reprise (RTO) | **4 h** : serveur neuf, pile en ligne, base et pièces restaurées depuis le distant | `preparer_serveur.sh` (~15 min), `deploy.sh` (~10 min), `restaurer.sh --depuis-distant` (le temps de rapatrier, quelques minutes par giga-octet), « Après une restauration » |
| Sauvegarde vérifiée | chaque matin | `manage.py verifier_sauvegardes` (ordonnanceur, 8 h 30) lit les marqueurs `.derniere-reussite-*` que `sauvegarder.sh` écrit après chaque réussite, et notifie les administrateurs — in-app et par e-mail — de ce qui manque ou date de plus de 26 h |
| Restauration prouvée | une fois avant l'ouverture, puis chaque trimestre | « Restauration dans un environnement isolé », avec `manage.py verifier_restauration` et un compte rendu daté |

La notification de sauvegarde en défaut est **critique** et se répète chaque
matin tant que le défaut dure ; son absence, un matin, ne prouve rien si
l'ordonnanceur lui-même est arrêté — `docker compose ps` doit montrer
`scheduler` sain.

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

#### Chiffrement : ce qui est protégé de quoi

Une phrase comme « les sauvegardes sont chiffrées » ne veut rien dire tant
qu'on n'a pas dit **quoi**, **contre qui**, et **où est la clé**. Voici
l'état exact.

| Ce qui existe | Chiffré ? | Contre quoi cela protège |
|---|---|---|
| Volume `sauvegardes` du serveur (`base/`, `base/mensuel/`, `pieces/`) | **Non** par défaut — **oui** avec `SAUVEGARDE_CLE_PUBLIQUE` (dumps seulement) | rien, par défaut : qui lit ce volume lit les dumps, donc les jetons de session et les secrets TOTP |
| Copie distante (`quotidien/`, `mensuel/`, `pieces/`) | **Oui** (rclone `crypt`, XSalsa20-Poly1305) | le tiers qui héberge le bucket, et quiconque obtient ses clés d'accès |
| Noms de fichiers sur le distant | **Non**, volontairement (`filename_encryption=off`) | — : c'est ce qui permet `--lister` et `--rapatrier` |
| Dump rapatrié par `--rapatrier` | **Non** : déchiffré à l'arrivée | — : `pg_restore` attend un dump lisible |

**Où est le secret, et ce que « hors serveur » veut dire.** Le chiffrement
de la copie distante est **symétrique** : c'est le serveur qui chiffre, il
lit le secret dans `/run/secrets/sauvegarde_chiffrement_cle` (secret
Compose alimenté par `SAUVEGARDE_CHIFFREMENT_CLE` du `.env`, `chmod 600`,
`root:root`). **Le serveur peut donc relire sa propre copie distante** —
c'est inhérent au procédé. « La clé se garde hors du serveur » signifie
qu'une **copie de récupération** est conservée ailleurs (gestionnaire de
mots de passe de la direction, copie imprimée au coffre), pour le jour où
le serveur est perdu avec son `.env`. Ce n'est pas une protection contre
un serveur compromis.

**À conserver pour pouvoir restaurer** — sans quoi la copie distante est
un tas d'octets : la clé, **le sel s'il est posé** (`SAUVEGARDE_CHIFFREMENT_SEL`,
qui est le second mot de passe du coffre rclone), et les réglages du
coffre (`filename_encryption=off`, `directory_name_encryption=false`). Un
coffre recréé avec d'autres réglages ne relira rien. Changer la clé rend
illisible ce qui a déjà été copié : on ne la change qu'en refaisant une
copie complète, et on garde l'ancienne tant que d'anciennes copies
comptent.

**Si l'exigence est que le serveur ne puisse pas déchiffrer** — parce qu'on
se protège d'un serveur compromis, pas seulement d'un hébergeur curieux —
le chiffrement symétrique n'y suffit pas, par construction. Posez alors
`SAUVEGARDE_CLE_PUBLIQUE` : chaque dump est chiffré **à la sortie de
`pg_dump`**, sur le serveur, avec une clé **publique** ; il n'existe en
clair nulle part, porte le suffixe `.enc`, et se restaure avec la clé
**privée**, qui n'est pas sur la machine.

```bash
# Sur un poste sûr, jamais sur le serveur : la clé privée reste ici.
openssl req -x509 -newkey rsa:4096 -days 3650 -nodes \
    -keyout sauvegardes-cle-privee.pem -out sauvegardes-cle-publique.pem \
    -subj "/CN=Sauvegardes JUSTI INNOV"
# Seul le certificat public part sur le serveur.
scp sauvegardes-cle-publique.pem root@<hôte>:/var/lib/docker/volumes/justi-innov_sauvegardes/_data/cle-publique.pem
# puis dans .env : SAUVEGARDE_CLE_PUBLIQUE=/sauvegardes/cle-publique.pem
```

La clé privée se garde comme la clé de chiffrement : coffre, et une copie.
La perdre, c'est perdre toutes les sauvegardes. Un dump `.enc` se déchiffre
là où elle est :

```bash
openssl smime -decrypt -binary -inform DER -in <dump>.dump.enc \
    -inkey sauvegardes-cle-privee.pem -out <dump>.dump
```

`restaurer.sh` refuse un `.enc` plutôt que de le passer à `pg_restore`, et
rappelle cette commande. Le miroir des justificatifs, lui, reste en clair
sur le volume : il vient de MinIO, qui les sert en clair de toute façon —
c'est le chiffrement de la copie distante qui les protège chez le tiers.

**Les sauvegardes déjà copiées en clair** — celles d'avant la mise en place
— ne se chiffrent pas rétroactivement : elles sont sur le distant telles
quelles. Deux choses à faire, dans cet ordre : supprimer depuis la console
du fournisseur (pas depuis le serveur, qui n'a plus le droit de supprimer)
les objets antérieurs à la bascule, puis lancer une copie complète pour que
le distant reparte d'un état entièrement chiffré. Tant que ce n'est pas
fait, considérez que ce qui est là-bas est lisible par l'hébergeur.

**Sans clé, rien ne part** vers le distant, et le journal dit pourquoi ;
`SAUVEGARDE_DISTANT_EN_CLAIR=1` lève ce refus, pour un essai seulement.

**Le serveur n'efface rien sur le distant.** Un serveur compromis — la clé
SSH de livraison, une faille — ne doit pas pouvoir emporter les
sauvegardes avec lui. La rotation des quotidiens n'est donc pas faite d'ici
(`SAUVEGARDE_DISTANT_ROTATION=0`, défaut) mais par une règle de cycle de
vie du bucket, et le compte donné au service **n'a pas le droit de
supprimer**. Un distant sans règle de cycle de vie accepte
`SAUVEGARDE_DISTANT_ROTATION=1`, en sachant ce qu'on y perd.

Le distant est un bucket S3 compatible (Backblaze B2, AWS, Scaleway, OVH,
Infomaniak, un MinIO ailleurs…), **chez un autre hébergeur ou dans une
autre région** que le serveur. Il est disposé ainsi ; les mensuels et les
pièces n'y sont jamais supprimés, les quotidiens le sont par le bucket :

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
| `SAUVEGARDE_CHIFFREMENT_CLE`, `SAUVEGARDE_CHIFFREMENT_SEL` | la clé du coffre (secret Compose, **obligatoire**, gardée aussi hors du serveur) et son sel facultatif |
| `SAUVEGARDE_DISTANT_ROTATION` | `0` (défaut) : le serveur n'efface rien là-bas, le bucket applique la rétention ; `1` : rotation des quotidiens faite d'ici |

**Backblaze B2, le choix retenu** (10 Go gratuits, sans carte bancaire ;
décision 51 de `docs/model-de-donnees.md`), pas à pas, dans la console B2 :

1. *Buckets › Create a Bucket* : nom unique (`sauvegardes-justi-innov`),
   **Private**, *Default Encryption* au choix (le contenu arrive déjà
   chiffré), *Object Lock* non requis. Notez la région de l'endpoint S3
   affiché (`s3.eu-central-003.backblazeb2.com` → région `eu-central-003`).
2. *Lifecycle Settings* du bucket : **Keep all versions** (le défaut :
   `mensuel/` et `pieces/` ne se suppriment jamais, et un objet écrasé
   garde sa version précédente — ce qui protège aussi d'un serveur qui
   réécrirait des dumps corrompus), puis *Use custom lifecycle rules* avec
   une seule règle, sur le préfixe `quotidien/` : *Days Till Hide* =
   `SAUVEGARDE_RETENTION_JOURS` (30), *Days Till Delete* = 1. C'est cette
   règle qui tient la rétention des quotidiens à la place du serveur.
3. *App Keys › Add a New Application Key* : restreinte **à ce bucket**,
   capacités `listBuckets, listFiles, readFiles, writeFiles` — **sans
   `deleteFiles`**. `keyID` → `SAUVEGARDE_DISTANT_CLE`, `applicationKey` →
   `SAUVEGARDE_DISTANT_SECRET` (affiché une seule fois).
4. Dans `.env` : `SAUVEGARDE_DISTANT_ENDPOINT=https://s3.<région>.backblazeb2.com`,
   `SAUVEGARDE_DISTANT_BUCKET=<nom du bucket>`,
   `SAUVEGARDE_DISTANT_REGION=<région>`, `SAUVEGARDE_DISTANT_FOURNISSEUR=Other`,
   et la clé de chiffrement : `SAUVEGARDE_CHIFFREMENT_CLE="$(openssl rand -base64 48)"`,
   aussitôt recopiée hors du serveur.

Restaurer une version antérieure d'un objet écrasé se fait depuis la
console B2 (*Browse Files › Show all versions*) ; le service, lui, ne voit
que la version courante.

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

### Après une restauration

Une base restaurée est **la base d'une autre date**. Elle contient les
jetons de session et les secrets TOTP de ce jour-là, et ignore tout ce qui
a été révoqué depuis : un compte désactivé hier revient actif, un jeton
révoqué hier redevient valable, un mot de passe changé hier redevient
l'ancien. Après toute restauration de la base **de la pile** :

```bash
docker compose -f docker-compose.prod.yml exec backend \
    python manage.py revoquer_sessions --tous --motif "restauration du <dump>"
```

puis relire l'historique des comptes (`Configuration › Historique`) entre
la date du dump et la restauration, et rejouer à la main ce qui s'y
trouvait : désactivations, réinitialisations de mot de passe et de second
facteur (« Double authentification »). La restauration elle-même est un
acte d'exploitation à consigner : date, dump, qui, pourquoi.

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

### Restauration dans un environnement isolé

Une sauvegarde qu'on n'a jamais restaurée n'est qu'un espoir ; une
sauvegarde copiée n'est pas une sauvegarde restaurée. **Une fois avant
l'ouverture aux pays, puis chaque trimestre**, la restauration se prouve
de bout en bout, dans une pile jetable qui ne touche ni la base, ni le
bucket, ni les destinataires de la production. Le compte rendu daté est
le livrable ; sans lui, rien n'est prouvé.

**1. Une pile jetable.** Sur le serveur (ou sur n'importe quelle machine
avec Docker), un second projet Compose, avec ses propres volumes, le
courrier en console et un bucket vide :

```bash
mkdir -p ~/restauration && cd ~/restauration
cp ~/justi-innov/deploy/docker-compose.prod.yml ~/justi-innov/deploy/{sauvegarder.sh,restaurer.sh,creer_role_applicatif.sql,Caddyfile} .
cp ~/justi-innov/deploy/.env .env
# Isolement : mêmes images (BACKEND_IMAGE, FRONTEND_IMAGE, IMAGE_TAG sont
# dans le .env, écrits par deploy.sh), autres volumes (autre nom de
# projet), courrier en console, aucun port public.
sed -i -e '/^EMAIL_BACKEND_CONSOLE=/d' -e 's/^EMAIL_HOST=.*/EMAIL_HOST=/' \
       -e '/^COMPOSE_PROJECT_NAME=/d' -e '/^COMPOSE_FILE=/d' .env
cat >> .env <<'EOF'
EMAIL_BACKEND_CONSOLE=1
COMPOSE_PROJECT_NAME=justi-restauration
COMPOSE_FILE=docker-compose.prod.yml:docker-compose.override.yml
EOF
cat > docker-compose.override.yml <<'EOF'
services:
  caddy:
    ports: []            # rien n'écoute sur Internet
EOF
docker compose up -d --wait db minio backend
```

Le projet `justi-restauration` a ses volumes (`justi-restauration_pgdata`,
`justi-restauration_sauvegardes`, …) : rien de commun avec la production.
Les services de sauvegarde ne sont pas démarrés (`up` ne nomme que `db`,
`minio` et `backend`) : rien ne repart vers le distant depuis cette pile.
Ne lancez jamais ici `sauvegarde-distante --une-fois`.

**2. Rapatrier et restaurer, depuis le distant** — c'est le chemin qui
servira le jour où le serveur est perdu, et le seul qui prouve que le coffre
se déchiffre avec la clé gardée hors du serveur :

```bash
docker compose run --rm sauvegarde-distante --lister
docker compose run --rm sauvegarde-distante --rapatrier justi_innov-<horodatage>.dump
docker compose run --rm sauvegarde-distante --rapatrier-pieces
./restaurer.sh justi_innov-<horodatage>.dump          # dans CE projet : la base jetable
./restaurer.sh --pieces                               # dans le bucket jetable
```

`restaurer.sh` lit `COMPOSE_PROJECT_NAME` et `COMPOSE_FILE` dans ce `.env`
: il demande de taper le nom de la base, et c'est la base jetable du projet
`justi-restauration` qu'il écrase — la production n'est pas touchée.
`--rapatrier` déchiffre le coffre avec `SAUVEGARDE_CHIFFREMENT_CLE` du
`.env` copié : pour prouver la clé gardée hors du serveur, remplacez-la
dans ce `.env` par la copie du gestionnaire de mots de passe. Notez
l'heure de début et de fin : c'est la mesure du délai de reprise.

**3. Vérifier — la commande dit non si une pièce manque :**

```bash
docker compose exec backend python manage.py verifier_restauration
```

Elle refuse de tourner si le courrier n'est pas en console, affiche les
décomptes (comptes par rôle, pays, dossiers et lignes par statut, entrées
d'audit et d'historique), **la date de la dernière entrée du journal
d'audit — la perte de données réelle de cette sauvegarde** —, ouvre
**chaque** pièce dans le bucket jetable et compare son empreinte SHA-256 à
la fiche. Code de sortie 0, ou une liste nommée de ce qui manque.
Comparez les décomptes à ceux de la production au moment du dump.

**4. Ouvrir l'application restaurée**, sans port public : un tunnel SSH
vers le conteneur (`ssh -L 8443:127.0.0.1:443 …` après avoir remis un
`ports: ["127.0.0.1:8443:443"]` sur `caddy` dans la surcharge), connexion
avec un compte du dump, un dossier justifié pris au hasard, sa pièce
ouverte. Les e-mails que l'application « enverrait » sont dans
`docker compose logs backend scheduler` — aucun ne part.

**5. Détruire la pile jetable**, volumes compris :

```bash
docker compose down -v && cd ~ && rm -rf ~/restauration
```

**6. Consigner** dans le journal d'exploitation (`docs/`, ou le projet
Claude « JUSTI INNOV ») : date, dump restauré (nom, taille), durée réelle
de 2 à 4, sortie complète de `verifier_restauration`, écarts constatés,
limites restantes. Un écart inexpliqué est un incident, pas une note de
bas de page.

## Après une fuite

Une sauvegarde lue par un tiers, un `.env` copié, un poste d'exploitation
compromis : ce qui est exposé, et ce qu'il faut faire, dans l'ordre. Deux
choses n'ouvrent pas les mêmes portes :

| Ce qui a fui | Ce que cela permet | Ce qui le ferme |
|---|---|---|
| **Un jeton d'API** (table `authtoken_token`, en clair dans tout dump) | entrer dans l'API **sans mot de passe ni second facteur**, avec les droits du compte, jusqu'à 30 jours après l'émission du jeton (`TOKEN_MAX_AGE_DAYS`) | `manage.py revoquer_sessions --tous --motif "…"` : tous les jetons sont retirés, chaque compte doit se reconnecter, et l'historique le dit |
| **Un secret TOTP** (`accounts_userprofile.totp_secret`, en clair) | calculer les codes du second facteur — mais **pas** entrer seul : il faut aussi le mot de passe, qui n'est stocké que haché (PBKDF2) | pour chaque compte enrôlé : `reset-2fa` par un administrateur puis réenrôlement par le titulaire (« Double authentification ») ; changer les mots de passe par prudence, un mot de passe faible devenant suffisant |
| **`.env` du serveur** | tout : base, stockage, courrier, distant, clé de chiffrement des sauvegardes | changer chaque secret, dans cet ordre : distant et clé de chiffrement (puis une copie complète), stockage MinIO (`AWS_*`, puis `ensure_bucket`), courrier (mot de passe d'application), `DJANGO_SECRET_KEY` (invalide les sessions Django, pas les jetons DRF), mot de passe Postgres ; puis `revoquer_sessions --tous` |
| **La clé SSH de livraison** | ce que peut le compte `deploy` (« Réduire les pouvoirs de la livraison ») | retirer la clé de `authorized_keys`, en générer une autre, remplacer le secret `DEPLOY_SSH_KEY` dans l'environnement GitHub |

Une restauration ancienne **réactive** des accès révoqués depuis : voir
« Après une restauration ».

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
