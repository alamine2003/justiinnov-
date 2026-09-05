---
name: verifier
description: Boucle de vérification complète de JUSTI INNOV avant un commit ou une livraison — suite backend sur base privée, migrations, catalogues, typage, lint, tests et build frontend, puis pile livrable et captures Playwright avec comptes jetables enrôlés en 2FA. À utiliser en fin de chantier ou quand on demande « vérifie tout ».
---

# Vérifier tout

Chaque étape doit être verte avant la suivante. Ne lancez qu'une suite
backend à la fois ; donnez-lui une base privée.

## Instructions

### Étape 1 : backend

```bash
cd "$(git rev-parse --show-toplevel)"
docker compose run --rm --entrypoint django-admin backend compilemessages -l en -v0 --ignore=.venv
docker compose run --rm --entrypoint sh backend -c 'python manage.py makemessages -l en --ignore=tests --no-obsolete --no-wrap -v0 && msgfmt --check --statistics -o /dev/null locale/en/LC_MESSAGES/django.po && msgattrib --untranslated locale/en/LC_MESSAGES/django.po && msgattrib --only-fuzzy locale/en/LC_MESSAGES/django.po'
docker compose run --rm -e POSTGRES_DB=justi_verif --entrypoint python backend manage.py makemigrations --check --dry-run
docker compose run --rm -e POSTGRES_DB=justi_verif -e EMAIL_BACKEND_CONSOLE=1 --entrypoint python backend manage.py test --noinput --parallel auto
```

Si `requirements.txt` ou le `Dockerfile` ont changé : `docker compose build backend` avant.

### Étape 2 : frontend

```bash
cd frontend && npx tsc -b && npm run lint && npm run test && npm run build
```

Zéro erreur, zéro avertissement.

### Étape 3 : pile livrable et captures

Générez des comptes jetables avec courriel `@innovpharma.net`, mot de passe
aléatoire et secret TOTP base32, dans `backend/seed_users.ci.json` (ignoré
par git ; modèle dans `.github/workflows/ci.yml`, étape « Générer des
comptes jetables »). Puis :

```bash
docker compose -f docker-compose.yml -f docker-compose.ci.yml up -d --build --wait --wait-timeout 300
docker compose -f docker-compose.yml -f docker-compose.ci.yml exec -T backend python manage.py seed_users --file seed_users.ci.json
cd frontend
export SHOT_BASE=http://127.0.0.1:8080 SHOT_OUT=/tmp/captures \
  SHOT_HQ_USER=siege.ci SHOT_HQ_PASSWORD=… SHOT_HQ_TOTP_SECRET=… \
  SHOT_COUNTRY_USER=togo.ci SHOT_COUNTRY_PASSWORD=… SHOT_COUNTRY_TOTP_SECRET=…
npx tsx scripts/shot-login.ts && npx tsx scripts/screenshot.ts && npx tsx scripts/shot-theme.mts
```

Les scripts échouent sur toute erreur console et toute attente non tenue.
Regardez au moins deux captures (`shot_login.png`, `shot_dossier_detail.png`).
Sur macOS, `timeout` n'existe pas : `perl -e 'alarm shift; exec @ARGV' 300 npx tsx …`.

### Étape 4 : revenir au mode développement

`docker compose up -d` remet le frontend Vite sur le port 5173.

### Étape 5 : rapport

Un tableau vérification / résultat, puis ce qui a échoué avec la sortie
brute. Ne dites jamais « vert » sans l'avoir vu.
