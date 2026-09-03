FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

# Docker ne déclare le conteneur prêt que lorsque l'API répond et voit sa
# base : `docker compose up --wait` et la livraison continue s'y fient. Le
# délai de grâce couvre les migrations appliquées au démarrage.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import sys, urllib.request; \
r = urllib.request.urlopen('http://127.0.0.1:8000/api/health/', timeout=4); \
sys.exit(0 if r.status == 200 else 1)"

ENTRYPOINT ["/app/entrypoint.sh"]