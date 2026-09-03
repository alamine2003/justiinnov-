#!/bin/sh
# Déploie une étiquette d'images sur ce serveur.
#
# Appelé par la livraison continue via SSH, mais tout aussi utilisable à la
# main pour revenir à une version précédente :
#
#   IMAGE_TAG=sha-abcdef123456 BACKEND_IMAGE=ghcr.io/org/depot-backend \
#   FRONTEND_IMAGE=ghcr.io/org/depot-frontend APP_DOMAIN=… ./deploy.sh
#
# Si GHCR_USER est défini, un jeton de registre est lu sur l'entrée standard.
set -eu

cd "$(dirname "$0")"

: "${IMAGE_TAG:?IMAGE_TAG manquant}"
: "${BACKEND_IMAGE:?BACKEND_IMAGE manquant}"
: "${FRONTEND_IMAGE:?FRONTEND_IMAGE manquant}"
export IMAGE_TAG BACKEND_IMAGE FRONTEND_IMAGE

if [ ! -f .env ]; then
  echo "✘ Aucun fichier .env : copiez .env.example et renseignez-le." >&2
  exit 1
fi

compose() {
  docker compose -f docker-compose.prod.yml "$@"
}

if [ -n "${GHCR_USER:-}" ]; then
  echo "→ Connexion au registre…"
  docker login ghcr.io -u "$GHCR_USER" --password-stdin
fi

echo "→ Récupération des images ${IMAGE_TAG}…"
compose pull --quiet

# La précédente étiquette, pour dire d'où l'on vient — et où revenir.
precedente="$(cat .deployed 2>/dev/null || echo "aucune")"
echo "→ Déploiement ${precedente} → ${IMAGE_TAG}"

# `--wait` ne rend la main que lorsque chaque service passe son contrôle de
# santé : les migrations sont appliquées et gunicorn répond. Sinon, il sort
# en erreur et les journaux disent pourquoi.
if ! compose up -d --remove-orphans --wait --wait-timeout 240; then
  echo "✘ La pile n'est pas devenue saine ; journaux du backend :" >&2
  compose logs --no-color --tail 100 backend >&2
  exit 1
fi

echo "$IMAGE_TAG" > .deployed

if [ -n "${GHCR_USER:-}" ]; then
  docker logout ghcr.io >/dev/null 2>&1 || true
fi

# Les images des versions précédentes restent pour un retour arrière rapide ;
# seules les couches orphelines partent.
docker image prune -f >/dev/null

echo "✔ ${IMAGE_TAG} en ligne."
compose ps
