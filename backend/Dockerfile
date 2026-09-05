FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# gettext : nécessaire à `compilemessages` (interface bilingue).
RUN apt-get update && apt-get install -y --no-install-recommends gettext && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Les dépendances s'installent en root dans le site-packages du système ; le
# pip de l'image de base suffit, on ne le remplace pas par un pip flottant.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Le serveur tourne sous un compte sans privilège : une faille dans une vue
# ou une dépendance ne donne pas root dans le conteneur. `media/` doit rester
# inscriptible pour le stockage local (sans MinIO, en développement).
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --create-home --shell /usr/sbin/nologin app

COPY --chown=app:app . .

RUN chmod +x /app/entrypoint.sh && mkdir -p /app/media && chown app:app /app/media

USER app

# Catalogue de traduction (interface bilingue) : le `.po` est versionné, le
# `.mo` compilé ici, dans l'image — jamais dans le dépôt (.gitignore). Un
# seul catalogue, `locale/` à la racine du projet (décision 42), compilé
# d'une commande ; `django-admin` sans les réglages du projet : rien à
# importer, aucune base à joindre. Après `USER app` : le `.mo` appartient au
# compte qui fait tourner le serveur, et l'entrypoint peut le recompiler
# sans erreur de droit.
RUN django-admin compilemessages -l en -v0

EXPOSE 8000

# Docker ne déclare le conteneur prêt que lorsque l'API répond et voit sa
# base : `docker compose up --wait` et la livraison continue s'y fient. Le
# délai de grâce couvre les migrations appliquées au démarrage.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import sys, urllib.request; \
r = urllib.request.urlopen('http://127.0.0.1:8000/api/health/', timeout=4); \
sys.exit(0 if r.status == 200 else 1)"

ENTRYPOINT ["/app/entrypoint.sh"]
