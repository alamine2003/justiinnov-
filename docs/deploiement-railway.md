# Déploiement sur Railway (voie de repli)

> La plateforme tourne aujourd'hui sur le serveur Hetzner (`deploy/`,
> domaine `178-105-215-49.sslip.io`) : Railway refuse la carte prépayée du
> groupe pour son abonnement. Ce document reste prêt pour le jour où une
> carte bancaire classique le permettra, ou pour un autre projet.

Sur [Railway](https://railway.com), sans serveur
à administrer ni nom de domaine à posséder, Railway construit les images
depuis GitHub à chaque poussée sur `main`, fournit un domaine
`*.up.railway.app` avec son certificat, la base Postgres et le stockage
objet des justificatifs. La pile Docker de `deploy/` (Caddy, MinIO,
sauvegardes, Grafana) reste le chemin pour un serveur dédié ; ce document
décrit l'autre.

```
navigateur ──https──▶ frontend (nginx, public) ──/api/──▶ backend (Django)
                                                          │        │
                                                     Postgres    Bucket
                      scheduler (run_scheduler) ──────────┘        │
                                                                   └── justificatifs
```

Le projet Railway compte **cinq éléments**, tous dans le même
environnement : trois services construits depuis le dépôt et deux
ressources fournies par Railway.

| Élément | Type | Source | Rôle |
|---|---|---|---|
| `frontend` | service, **domaine public** | dépôt, *Root Directory* `/frontend` | nginx : interface, limitation de débit, en-têtes de sécurité, relais de `/api/` vers le backend par le réseau privé |
| `backend` | service, sans domaine | dépôt, *Root Directory* `/backend` | Django + gunicorn ; migrations au démarrage (`entrypoint.sh`) |
| `scheduler` | service, sans domaine | dépôt, *Root Directory* `/backend`, config `/backend/railway.scheduler.json` | `manage.py run_scheduler` : alertes et rapports périodiques |
| `Postgres` | base Railway | — | la base ; `DATABASE_URL` est fournie |
| `Bucket` | stockage objet Railway (S3) | — | les pièces justificatives ; identifiants fournis |

Le backend n'est joignable que par le frontend, sur le réseau privé
(`backend.railway.internal:8000`) : comme derrière Caddy, `/admin/` n'est
pas exposé et l'API ne répond qu'à travers nginx.

Chaque service lit sa configuration dans le dépôt (`railway.json` de son
répertoire racine, ou le fichier désigné) : Dockerfile, contrôle de santé,
politique de redémarrage, chemins surveillés — une poussée qui ne touche
que `frontend/` ne reconstruit pas le backend.

## Ce qui change par rapport à la pile `deploy/`

- **TLS et domaine** : Railway termine TLS et transmet
  `X-Forwarded-Proto: https` ; nginx le relaie, Django l'accepte
  (`SECURE_PROXY_SSL_HEADER`). Pas de Caddy, pas de `APP_DOMAIN`.
- **Stockage** : le Bucket Railway remplace MinIO, par les mêmes variables
  `AWS_*` ; `ensure_bucket` trouve le bucket déjà créé et n'y touche pas.
- **Sauvegardes** : plus de `sauvegarder.sh`. Activez les sauvegardes de la
  base dans l'onglet *Backups* du service Postgres (quotidiennes, à
  conserver au moins 30 jours) ; le Bucket ne se sauvegarde pas seul — un
  miroir périodique vers un second stockage reste à organiser avant
  d'ouvrir la plateforme aux pays (« Copie hors machine », `deploy/README.md`).
- **Supervision** : pas de Prometheus ni de Grafana (`SUPERVISION=0`) ; les
  métriques, les journaux et les redémarrages se lisent dans Railway.
- **Rôle applicatif sans DDL** : non appliqué, le service se connecte avec
  le compte fourni par Railway. `creer_role_applicatif.sql` reste
  applicable à la main si on y tient.
- **Adresse du client** : nginx croit `X-Forwarded-For` venant du
  mandataire de Railway (`NGINX_TRUSTED_PROXY=0.0.0.0/0` — seul ce
  mandataire atteint le conteneur) et Django lit l'adresse deux sauts en
  arrière (`DJANGO_NUM_PROXIES=2`), comme derrière Caddy puis nginx.

## Mise en place

1. **Le projet.** *New Project › Deploy from GitHub repo*, dépôt
   `alamine2003/justiinnov-`, branche `main`. Railway crée un premier
   service : nommez-le `backend` et, dans *Settings › Source*, posez
   *Root Directory* à `/backend`. Ne lui donnez pas de domaine.
2. **La base et le bucket.** *Create › Database › PostgreSQL*, puis
   *Create › Bucket* (la région ne se change plus ensuite ; prenez celle
   des services). Nommez-les `Postgres` et `Bucket` : ce sont les noms
   utilisés par les références ci-dessous.
3. **Les variables partagées.** *Project Settings › Shared Variables* :
   celles qui servent au backend et à l'ordonnanceur ensemble, pour ne les
   saisir qu'une fois (tableau plus bas). Les secrets se génèrent avec
   `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
4. **Le backend.** Dans ses *Variables*, ajoutez les références aux
   variables partagées et `PORT=8000`. Le premier déploiement applique les
   migrations et crée la table de cache ; il est sain quand `/api/health/`
   répond (jusqu'à 5 min).
5. **L'ordonnanceur.** *Create › GitHub Repo*, même dépôt, service nommé
   `scheduler`, *Root Directory* `/backend`, et dans *Settings › Config-as-code*
   le chemin `/backend/railway.scheduler.json` (c'est lui qui remplace
   l'entrypoint par `run_scheduler`). Mêmes variables que le backend, sans
   `PORT`. Il n'a ni domaine ni contrôle de santé.
6. **Le frontend.** *Create › GitHub Repo*, même dépôt, service `frontend`,
   *Root Directory* `/frontend`, variables du tableau « frontend ». Puis
   *Settings › Networking › Generate Domain*, port **80**. Le domaine obtenu
   (`RAILWAY_PUBLIC_DOMAIN`) est celui de la plateforme ; les variables du
   backend le lisent par référence, rien à recopier.
7. **Le premier compte.** Posez sur le backend, le temps d'un démarrage,
   `DJANGO_CREATE_SUPERUSER=1`, `DJANGO_SUPERUSER_USERNAME`,
   `DJANGO_SUPERUSER_EMAIL` (une adresse en `ALLOWED_EMAIL_DOMAINS`) et
   `DJANGO_SUPERUSER_PASSWORD` : l'entrypoint crée un `super_admin` au mot
   de passe provisoire, à remplacer à la première connexion. Retirez ensuite
   ces quatre variables. Les autres comptes se créent depuis l'écran des
   comptes, ou par `seed_users` depuis un shell sur le service
   (`railway ssh --service backend`, avec un fichier collé dans `/tmp`).
8. **Vérifier** : `https://<domaine>/api/health/` répond `200` ; la
   connexion fonctionne ; un justificatif déposé apparaît dans le Bucket
   (*Data* du service Bucket) ; les journaux du `scheduler` montrent les
   trois tâches planifiées et un battement chaque minute.

Ensuite, chaque poussée sur `main` redéploie ce qui a changé. La CI de
GitHub (`ci.yml`) tourne toujours sur les pull requests et sur `main`, mais
Railway n'attend pas son verdict : gardez la règle « rien n'entre dans
`main` sans passer par une pull request verte ».

## Variables

**Partagées** (backend et ordonnanceur) — dans *Shared Variables*, puis
référencées `${{shared.NOM}}` dans chaque service :

| Variable | Valeur | Remarque |
|---|---|---|
| `DJANGO_SECRET_KEY` | secret généré, 64 caractères | jamais réutilisé ailleurs |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | connexion par le réseau privé, sans TLS ; `DATABASE_PUBLIC_URL` n'est pas à utiliser |
| `DJANGO_ALLOWED_HOSTS` | `${{frontend.RAILWAY_PUBLIC_DOMAIN}},healthcheck.railway.app` | le second est l'hôte présenté par le contrôle de santé de Railway ; `127.0.0.1` et `backend` sont ajoutés d'office |
| `CORS_ALLOWED_ORIGINS` | `https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}` | |
| `APP_BASE_URL` | `https://${{frontend.RAILWAY_PUBLIC_DOMAIN}}` | liens dans les e-mails |
| `DJANGO_NUM_PROXIES` | `2` | mandataire Railway, puis nginx |
| `DJANGO_HSTS_SECONDS` | `31536000` | Railway n'émet pas HSTS : Django le fait |
| `AWS_S3_ENDPOINT_URL` | `${{Bucket.ENDPOINT}}` | |
| `AWS_ACCESS_KEY_ID` | `${{Bucket.ACCESS_KEY_ID}}` | |
| `AWS_SECRET_ACCESS_KEY` | `${{Bucket.SECRET_ACCESS_KEY}}` | |
| `AWS_STORAGE_BUCKET_NAME` | `${{Bucket.BUCKET}}` | le nom réel, suffixé par Railway |
| `AWS_DEFAULT_REGION` | `${{Bucket.REGION}}` | lue par boto3 |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | serveur SMTP de l'entreprise | **obligatoire** : sans SMTP, le backend refuse de démarrer. Tant qu'il n'y en a pas, `EMAIL_BACKEND_CONSOLE=1` à la place — les alertes et rapports vont alors dans les journaux, et personne ne les lit |
| `DJANGO_TIME_ZONE` | `Africa/Dakar` (ou celui du siège) | heures des rapports (`SCHEDULE_*`) |
| `ALLOWED_EMAIL_DOMAINS` | `innovpharma.net` | défaut, à poser seulement pour en ajouter |
| `SUPERVISION` | `0` | pas de Grafana ici |

**backend** : les références aux partagées, plus `PORT=8000` et, selon la
taille du service, `GUNICORN_WORKERS` (2 par défaut, ~120 Mo chacun).

**scheduler** : les références aux partagées, rien d'autre.

**frontend** :

| Variable | Valeur | Remarque |
|---|---|---|
| `PORT` | `80` | port d'écoute de nginx, du contrôle de santé et du domaine |
| `NGINX_API_UPSTREAM` | `http://${{backend.RAILWAY_PRIVATE_DOMAIN}}:8000` | le backend, par le réseau privé |
| `NGINX_RESOLVER_IPV6` | `on` | le réseau privé de Railway répond aussi en IPv6 |
| `NGINX_TRUSTED_PROXY` | `0.0.0.0/0` | croire `X-Forwarded-For` du mandataire Railway (seul à atteindre le conteneur) |

`NGINX_RESOLVER` n'a pas à être posé : nginx prend le résolveur du
conteneur (`/etc/resolv.conf`), qui est celui du réseau privé.

## Exploitation

- **Journaux** : onglet *Logs* de chaque service. Ceux du backend portent
  les accès gunicorn ; ceux de l'ordonnanceur, chaque tâche lancée.
- **Redéployer sans changement** : *Deployments › Redeploy* ; **revenir en
  arrière** : *Rollback* sur un déploiement précédent (les migrations ne se
  défont pas : même limite que `deploy/README.md`).
- **Migration longue** : le contrôle de santé attend 5 min
  (`healthcheckTimeout`) ; au-delà, jouez-la à la main depuis
  `railway ssh --service backend` (`python manage.py migrate`) puis
  redéployez.
- **Shell sur le service** : `railway ssh --service backend`, ou
  `railway run --service backend python manage.py <commande>` depuis le
  poste, avec les variables du service.
- **Réinitialiser une double authentification** dont le dernier
  `super_admin` a perdu le téléphone : la procédure shell de
  `deploy/README.md` (« Réinitialiser un enrôlement ») s'applique telle
  quelle depuis `railway ssh`.
- **Domaine propre**, le jour où il y en a un : *Settings › Networking ›
  Custom Domain* sur `frontend`, un enregistrement CNAME chez le
  registraire, et les références `RAILWAY_PUBLIC_DOMAIN` ci-dessus à
  remplacer par ce domaine (`DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`,
  `APP_BASE_URL`).
