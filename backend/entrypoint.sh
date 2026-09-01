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
    python manage.py shell -c "
import os
from django.contrib.auth.models import User
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
if User.objects.filter(username=username).exists():
    print(f'Superutilisateur {username} déjà présent')
else:
    User.objects.create_superuser(
        username,
        os.environ.get('DJANGO_SUPERUSER_EMAIL', ''),
        os.environ['DJANGO_SUPERUSER_PASSWORD'],
    )
    print(f'Superutilisateur {username} créé')
"
  fi
fi

echo "→ Démarrage du serveur…"
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3