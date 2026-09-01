#!/bin/sh
set -e

echo "→ Application des migrations…"
python manage.py migrate --noinput

if [ "$DJANGO_CREATE_SUPERUSER" = "1" ]; then
  python manage.py shell -c "
from django.contrib.auth.models import User
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print('Superuser admin/admin123 créé')
else:
    print('Superuser admin déjà présent')
"
fi

echo "→ Démarrage du serveur…"
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3