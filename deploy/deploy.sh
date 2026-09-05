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
#
# Si la nouvelle pile ne devient pas saine dans le délai imparti, l'étiquette
# précédente (lue dans `.deployed`) est rétablie avant de sortir en erreur :
# une livraison ratée ne laisse pas la plateforme hors ligne.
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

# Lecture de .env sans `source` : il contient des cadences cron
# (`0 * * * *`) qu'un shell développerait. Dernière occurrence, guillemets
# retirés.
valeur() {
  grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e "s/^'\(.*\)'\$/\1/" -e 's/^"\(.*\)"$/\1/'
}

# Fichiers Compose : docker-compose.prod.yml seul, ou la liste COMPOSE_FILE
# du .env quand une surcharge locale s'y ajoute (README.md, « Surcharge
# locale »). Compose lit lui-même COMPOSE_FILE dans .env — mais un `-f`
# explicite la ferait taire ; on ne le passe donc que si elle est absente.
fichiers_compose="$(valeur COMPOSE_FILE)"
compose() {
  if [ -n "$fichiers_compose" ]; then
    docker compose "$@"
  else
    docker compose -f docker-compose.prod.yml "$@"
  fi
}

# Profil `supervision` (Prometheus, exporteurs, Grafana) : SUPERVISION=1
# dans .env fait foi. COMPOSE_PROFILES, que Compose lit lui-même dans .env,
# est exporté ici pour que ce script et Compose voient la même chose ; un
# COMPOSE_PROFILES du .env qui contredit SUPERVISION est signalé, parce que
# `docker compose` lancé à la main le suivrait, lui.
supervision="$(valeur SUPERVISION)"
profils_env="$(valeur COMPOSE_PROFILES)"
profils_sans="$(printf '%s' "$profils_env" | tr ',' '\n' | grep -vx 'supervision' | paste -sd, - || true)"
if [ "$supervision" = "1" ]; then
  export COMPOSE_PROFILES="${profils_sans:+$profils_sans,}supervision"
  case ",$profils_env," in
    *,supervision,*) ;;
    *) echo "⚠ SUPERVISION=1 mais COMPOSE_PROFILES ne contient pas « supervision » dans .env : ajoutez COMPOSE_PROFILES=supervision, sinon « docker compose » lancé à la main ignorera Grafana." >&2 ;;
  esac
else
  export COMPOSE_PROFILES="$profils_sans"
  case ",$profils_env," in
    *,supervision,*) echo "⚠ COMPOSE_PROFILES contient « supervision » mais SUPERVISION n'est pas à 1 dans .env : la supervision reste désactivée (Caddy ne route pas /grafana/) ; mettez les deux d'accord." >&2 ;;
  esac
fi

# La configuration se vérifie avant de tirer quoi que ce soit : une variable
# manquante dans .env (`${X:?X manquant}`) ou une surcharge mal formée se
# découvre ici, avec son nom, et non au milieu d'un `up` qui laisserait la
# pile à moitié remplacée.
echo "→ Vérification de la configuration Compose…"
if ! erreurs="$(compose config -q 2>&1)"; then
  variable="$(printf '%s\n' "$erreurs" | grep -o 'required variable [A-Za-z0-9_]*' | head -1 | cut -d' ' -f3 || true)"
  if [ -n "$variable" ]; then
    echo "✘ La variable ${variable} manque (ou est vide) dans .env — voir .env.example." >&2
  else
    echo "✘ Configuration Compose invalide (fichiers : ${fichiers_compose:-docker-compose.prod.yml})." >&2
  fi
  printf '%s\n' "$erreurs" | sed 's/^/  /' >&2
  exit 1
fi

# Une sauvegarde qui reste sur la machine n'en est pas une : on le dit à
# chaque livraison, sans bloquer — c'est la mise en production que la
# procédure (README.md, « Copie hors machine ») conditionne, pas le script.
if [ -z "$(valeur SAUVEGARDE_DISTANT_ENDPOINT)" ]; then
  echo "⚠ AUCUNE COPIE HORS MACHINE des sauvegardes : SAUVEGARDE_DISTANT_ENDPOINT est vide dans .env. Obligatoire avant toute mise en production (README.md, « Copie hors machine »)." >&2
fi

if [ "$supervision" = "1" ]; then
  echo "→ Supervision activée (profil Compose « supervision »)."
else
  echo "→ Supervision désactivée (SUPERVISION≠1) : Prometheus, exporteurs et Grafana ne sont pas lancés."
fi

if [ -n "${GHCR_USER:-}" ]; then
  echo "→ Connexion au registre…"
  docker login ghcr.io -u "$GHCR_USER" --password-stdin
fi

echo "→ Récupération des images ${IMAGE_TAG}…"
compose pull --quiet

# La précédente étiquette, pour dire d'où l'on vient — et où revenir.
precedente="$(cat .deployed 2>/dev/null || true)"
echo "→ Déploiement ${precedente:-aucune} → ${IMAGE_TAG}"

# Quand `--wait` échoue, dire lequel des services n'est pas sain — et
# pourquoi. Le backend n'est pas le seul à pouvoir bloquer : Grafana sans mot
# de passe, Caddy sans domaine, Prometheus sans jeton, une sauvegarde dont le
# script manque. Chaque service qui n'est pas « running » (et « healthy »
# s'il a un contrôle de santé) livre ses cent dernières lignes.
diagnostiquer() {
  echo "── État de la pile ──" >&2
  compose ps -a >&2
  compose ps -a --format '{{.Service}} {{.State}} {{.Health}}' | while read -r service etat sante; do
    case "${etat}/${sante:-}" in
      running/healthy|running/) ;;
      *)
        echo "── Journaux de ${service} (${etat}${sante:+, $sante}) ──" >&2
        compose logs --no-color --tail 100 "$service" >&2
        ;;
    esac
  done
}

# `--wait` ne rend la main que lorsque chaque service passe son contrôle de
# santé : les migrations sont appliquées et gunicorn répond. Sinon, il sort
# en erreur et les journaux disent pourquoi.
if ! compose up -d --remove-orphans --wait --wait-timeout 240; then
  echo "✘ La pile ${IMAGE_TAG} n'est pas devenue saine." >&2
  diagnostiquer

  if [ -n "$precedente" ] && [ "$precedente" != "$IMAGE_TAG" ]; then
    echo "↩ Retour à l'étiquette précédente ${precedente}…" >&2
    export IMAGE_TAG="$precedente"
    # Les images précédentes sont encore sur le serveur (`image prune` ne
    # retire que les couches orphelines) ; sinon elles sont retirées du
    # registre. Une migration qui n'a fait qu'ajouter se lit avec le code
    # précédent ; voir deploy/README.md pour les autres cas.
    if compose up -d --remove-orphans --wait --wait-timeout 240; then
      echo "↩ ${precedente} rétablie : la livraison est annulée, pas la plateforme." >&2
    else
      echo "✘ Le retour à ${precedente} a échoué lui aussi : intervention manuelle requise." >&2
      diagnostiquer
    fi
  else
    echo "✘ Aucune étiquette précédente à rétablir (.deployed absent)." >&2
  fi

  if [ -n "${GHCR_USER:-}" ]; then
    docker logout ghcr.io >/dev/null 2>&1 || true
  fi
  exit 1
fi

echo "$IMAGE_TAG" > .deployed

# Supervision désactivée après avoir été active : `up` sans le profil ne
# touche pas aux conteneurs d'un profil inactif (ils ne sont pas orphelins
# pour Compose), Grafana tournerait sans être routé. On les arrête, en
# gardant leurs volumes pour une réactivation.
if [ "$supervision" != "1" ]; then
  if COMPOSE_PROFILES="${COMPOSE_PROFILES:+$COMPOSE_PROFILES,}supervision" compose ps -q prometheus postgres-exporter node-exporter grafana 2>/dev/null | grep -q .; then
    echo "→ Arrêt des services de supervision, désactivés dans .env…"
    COMPOSE_PROFILES="${COMPOSE_PROFILES:+$COMPOSE_PROFILES,}supervision" compose stop prometheus postgres-exporter node-exporter grafana
  fi
fi

if [ -n "${GHCR_USER:-}" ]; then
  docker logout ghcr.io >/dev/null 2>&1 || true
fi

# Les images des versions précédentes restent pour un retour arrière rapide ;
# seules les couches orphelines partent.
docker image prune -f >/dev/null

echo "✔ ${IMAGE_TAG} en ligne."
compose ps
