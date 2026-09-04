#!/bin/sh
set -e

echo "→ Application des migrations…"
python manage.py migrate --noinput

echo "→ Table de cache (limitation de débit partagée entre workers)…"
python manage.py createcachetable

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
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --worker-class gthread \
  --workers "${GUNICORN_WORKERS:-2}" \
  --threads "${GUNICORN_THREADS:-4}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --graceful-timeout 30 \
  --max-requests 1000 --max-requests-jitter 100 \
  --worker-tmp-dir /dev/shm \
  --access-logfile - \
  --forwarded-allow-ips '*'
