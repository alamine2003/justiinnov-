# Simulation

Deux scripts qui jouent l'application comme ses utilisateurs, contre une
pile jetable (`docker-compose.ci.yml`) peuplée par `seed_users` et
`seed_demo --base-jetable`. Ils servent à l'agent `simulateur` et à toute
personne qui veut voir l'application tenir un usage réel.

## Comptes

Les scripts lisent un fichier JSON désigné par `SIM_COMPTES`, jamais
versionné : le même contenu que `backend/seed_users.ci.json`, réduit à ce
qu'il faut pour se connecter.

```json
{
  "siege.ci": {"password": "…", "totp_secret": "…", "role": "super_admin"},
  "admin.ci": {"password": "…", "totp_secret": "…", "role": "admin"},
  "dm.ci":    {"password": "…", "totp_secret": "…", "role": "dm"},
  "df.ci":    {"password": "…", "totp_secret": "…", "role": "df"},
  "ci1.ci":   {"password": "…", "totp_secret": "…", "role": "manager", "country": "CI"},
  "ci2.ci":   {"password": "…", "totp_secret": "…", "role": "manager", "country": "CI"},
  "togo.ci":  {"password": "…", "totp_secret": "…", "role": "manager", "country": "TG"},
  "tg3.ci":   {"password": "…", "totp_secret": "…", "role": "manager", "country": "TG"},
  "tg2.ci":   {"password": "…", "totp_secret": "…", "role": "manager", "country": "TG", "team": ["Équipe Lomé"]}
}
```

Le code TOTP est calculé par `pyotp` dans le conteneur `backend`
(`docker compose … exec backend python -c "import pyotp…"`) : rien à
installer sur la machine. `SIM_COMPOSE` (défaut : `docker-compose.yml
docker-compose.ci.yml`) nomme les fichiers Compose.

## Mise en service d'une filiale

```bash
SIM_COMPTES=/chemin/comptes.json python3 simulation/scenario.py http://127.0.0.1:8000
```

88 étapes attendues avec leur code : comptes du siège, ouverture d'un pays,
référentiel, enveloppes et sous-enveloppe bloquante, taux, dossier, lignes,
pièces (doublon, trop grosse, format refusé, HTML déguisé), soumission avec
et sans pièce, mise en contrôle, contrôle des pièces, justification
partielle, refus motivé et sans motif, interdits du manager, réallocation
(quatre yeux, immuable), réouverture et notification, import simulé, réel
et réimport, exports par mois, lectures par rôle, bilinguisme,
`notify_alerts`. Le script termine par `N étapes OK, M KO` avec le détail
de chaque KO.

## Charge : 30 utilisateurs, deux pays, cinq rôles

```bash
SIM_COMPTES=/chemin/comptes.json python3 simulation/charge.py http://127.0.0.1:8000 90 1.0   # gunicorn direct, réflexion 1 s
SIM_COMPTES=/chemin/comptes.json python3 simulation/charge.py http://127.0.0.1:8080 60 0     # derrière Caddy et nginx, sans pause
```

Vingt managers (deux comptes ivoiriens, trois togolais dont un cloisonné par
équipe), quatre DM, quatre DF, deux administrateurs. Par route : nombre,
réussites, p50, p95, p99, max, codes ; premiers refus ; erreurs réseau ;
violations de cloisonnement (un manager qui verrait un autre pays ou une
autre équipe, ou qui obtiendrait autre chose que 404 sur un dossier
étranger) ; sondes CPU et mémoire des conteneurs ; connexions PostgreSQL.

Pièges : la limite `user` de DRF (2 000 requêtes/heure) bloque un compte
une heure — `manage.py shell -c "from django.core.cache import cache;
cache.clear()"` sur la pile jetable ; la connexion est limitée à 10 par
minute et par adresse.

## Courses

Les scénarios à la seconde près sont des tests : `manage.py test
expenses.tests.test_verrous budget.tests.test_verrous
accounts.tests.test_verrous_totp`, sur une base privée.
