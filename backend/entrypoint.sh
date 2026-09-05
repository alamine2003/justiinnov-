#!/bin/sh
set -e

# Les migrations et la table de cache créent des tables : c'est du DDL, que
# le rôle applicatif à moindre privilège (deploy/creer_role_applicatif.sql)
# n'a pas le droit de faire. Si POSTGRES_MIGRATION_USER est défini, ces deux
# commandes — et elles seules — tournent avec le rôle propriétaire ; le
# serveur, lui, garde POSTGRES_USER. Avec une base désignée par DATABASE_URL,
# c'est DATABASE_MIGRATION_URL qui joue ce rôle.
#
# Le mot de passe du propriétaire arrive de préférence par un secret Compose
# (POSTGRES_MIGRATION_PASSWORD_FILE, monté sous /run/secrets par
# deploy/docker-compose.prod.yml) : il n'est alors ni dans l'environnement
# du serveur ni dans `docker inspect`. POSTGRES_MIGRATION_PASSWORD reste
# accepté pour un lancement à la main.
mot_de_passe_proprietaire() {
  if [ -n "${POSTGRES_MIGRATION_PASSWORD_FILE:-}" ] && [ -s "$POSTGRES_MIGRATION_PASSWORD_FILE" ]; then
    cat "$POSTGRES_MIGRATION_PASSWORD_FILE"
  else
    printf '%s' "${POSTGRES_MIGRATION_PASSWORD:-}"
  fi
}

en_tant_que_proprietaire() {
  if [ -n "${DATABASE_MIGRATION_URL:-}" ]; then
    env DATABASE_URL="$DATABASE_MIGRATION_URL" "$@"
  elif [ -n "${POSTGRES_MIGRATION_USER:-}" ]; then
    if [ -n "${DATABASE_URL:-}" ]; then
      echo "⚠ POSTGRES_MIGRATION_USER est ignoré : DATABASE_URL prime. Définissez DATABASE_MIGRATION_URL."
    fi
    env POSTGRES_USER="$POSTGRES_MIGRATION_USER" \
      POSTGRES_PASSWORD="$(mot_de_passe_proprietaire)" "$@"
  else
    "$@"
  fi
}

# En développement, le code est monté en volume : le `.mo` compilé dans
# l'image est masqué, et un `.po` modifié doit se recompiler. Un seul
# catalogue, `locale/` à la racine du projet (décision 42) : quelques
# dizaines de millisecondes. `django-admin` sans réglages du projet : aucune
# base à joindre. Un `.venv` du poste, monté avec le code, porterait les
# catalogues de Django lui-même : il est ignoré.
echo "→ Compilation des traductions…"
django-admin compilemessages -l en -v0 --ignore=.venv

echo "→ Application des migrations…"
en_tant_que_proprietaire python manage.py migrate --noinput

echo "→ Table de cache (limitation de débit partagée entre workers)…"
en_tant_que_proprietaire python manage.py createcachetable

echo "→ Stockage des justificatifs…"
python manage.py ensure_bucket

# Compte d'amorçage optionnel. Les comptes réels sont créés par
# `python manage.py seed_users` ; aucun mot de passe n'est codé en dur ici.
if [ "$DJANGO_CREATE_SUPERUSER" = "1" ]; then
  if [ -z "$DJANGO_SUPERUSER_PASSWORD" ]; then
    echo "⚠ DJANGO_CREATE_SUPERUSER=1 mais DJANGO_SUPERUSER_PASSWORD est vide : compte non créé."
  else
    # L'API refuse un compte sans profil : le superutilisateur reçoit le rôle
    # super_admin, et son mot de passe, distribué par l'environnement, est
    # provisoire — la plateforme reste fermée tant qu'il n'est pas remplacé.
    python manage.py shell -c "
import os
from django.contrib.auth.models import User
from accounts.models import UserProfile
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
user = User.objects.filter(username=username).first()
if user is None:
    user = User.objects.create_superuser(
        username,
        os.environ.get('DJANGO_SUPERUSER_EMAIL', ''),
        os.environ['DJANGO_SUPERUSER_PASSWORD'],
    )
    print(f'Superutilisateur {username} créé')
else:
    print(f'Superutilisateur {username} déjà présent')
_, created = UserProfile.objects.get_or_create(
    user=user, defaults={'role': 'super_admin', 'must_change_password': True}
)
if created:
    print(f'Profil super_admin créé pour {username} (mot de passe provisoire)')
"
  fi
fi

# Compteurs Prometheus partagés entre les workers gunicorn : chaque
# processus écrit les siens dans PROMETHEUS_MULTIPROC_DIR (mémoire partagée,
# /dev/shm/prometheus en production, voir deploy/.env.example) et le
# collecteur les agrège. Le dossier est créé puis vidé à chaque démarrage :
# les fichiers d'un processus mort — les commandes ci-dessus, le conteneur
# précédent — fausseraient les compteurs. Sans la variable, rien à faire :
# django-prometheus reste en mode simple, comme en développement.
if [ -n "${PROMETHEUS_MULTIPROC_DIR:-}" ]; then
  echo "→ Compteurs Prometheus dans ${PROMETHEUS_MULTIPROC_DIR}…"
  mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
  find "$PROMETHEUS_MULTIPROC_DIR" -mindepth 1 -delete
fi

echo "→ Démarrage du serveur…"
# Réglable par l'environnement, sans reconstruire l'image (voir
# deploy/.env.example). Workers gthread : chaque worker sert plusieurs
# requêtes à la fois, ce qui absorbe les téléchargements de justificatifs
# sans multiplier les processus ; le contexte de requête de `core/signals.py`
# est porté par des contextvars, donc sûr entre threads. Les workers sont
# recyclés périodiquement (fuites mémoire de longue durée) et leurs fichiers
# de battement vont en mémoire partagée, pas sur disque. Les en-têtes
# X-Forwarded-* sont acceptés de tout proxy : c'est Django qui les lit
# (SECURE_PROXY_SSL_HEADER, DJANGO_NUM_PROXIES), derrière Caddy et nginx.
# Ce qui ne tient pas sur une ligne de commande — les crochets Prometheus —
# est dans gunicorn.conf.py, à côté de manage.py.
exec gunicorn -c gunicorn.conf.py config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --worker-class gthread \
  --workers "${GUNICORN_WORKERS:-2}" \
  --threads "${GUNICORN_THREADS:-4}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --graceful-timeout 30 \
  --max-requests 10000 --max-requests-jitter 1000 \
  --worker-tmp-dir /dev/shm \
  --access-logfile - \
  --forwarded-allow-ips '*'
