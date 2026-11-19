#!/bin/sh
# La pile jetable de `repeter_la_restauration.sh`, telle que Compose la
# résout vraiment (décision 131). Demande Docker Compose ; rien ne démarre.
#
#   deploy/tests/test_pile_jetable.sh
#
# Les tests à doublures (`test_repeter_la_restauration.sh`) vérifient ce que
# le script écrit et d'où il appelle docker. Celui-ci fait lire le résultat
# à Compose lui-même — `docker compose config`, au moment où le script
# démarrerait la pile — à partir d'un .env de production qui désigne une
# base, un Redis et un serveur de courrier extérieurs, et d'un shell qui
# exporte le projet de la production. Aucun service ne doit y mener.
set -eu

ICI="$(cd "$(dirname "$0")" && pwd)"
REEL="$(command -v docker)" || { echo "✘ docker introuvable" >&2; exit 2; }

BAC="$(mktemp -d)"
trap 'rm -rf "$BAC"' EXIT
mkdir -p "$BAC/bin" "$BAC/maison"
cp -R "$ICI/.." "$BAC/exploitation"
rm -f "$BAC/exploitation/.env"

# Ce que docker-compose.prod.yml exige, plus ce qui mènerait hors de la pile.
# Les valeurs qui ressemblent à des secrets sont tirées au sort (GitGuardian).
cat > "$BAC/exploitation/.env" <<EOF
BACKEND_IMAGE=ghcr.io/ci/backend
FRONTEND_IMAGE=ghcr.io/ci/frontend
IMAGE_TAG=ci
APP_DOMAIN=ci.invalid
ACME_EMAIL=ci@ci.invalid
APP_BASE_URL=https://ci.invalid
CORS_ALLOWED_ORIGINS=https://ci.invalid
DJANGO_ALLOWED_HOSTS=ci.invalid
DJANGO_SECRET_KEY=$(openssl rand -hex 32)
DEFAULT_FROM_EMAIL=ci@ci.invalid
POSTGRES_PASSWORD=$(openssl rand -hex 16)
AWS_ACCESS_KEY_ID=ci-cle
AWS_SECRET_ACCESS_KEY=$(openssl rand -hex 16)
GRAFANA_ADMIN_PASSWORD=$(openssl rand -hex 8)
SAUVEGARDE_DISTANT_ENDPOINT=https://ci.invalid
SAUVEGARDE_CHIFFREMENT_CLE=$(openssl rand -hex 16)
DATABASE_URL=postgresql://justi_app:x@base-de-production.invalid:5432/justi_innov
DATABASE_MIGRATION_URL=postgresql://justi:x@base-de-production.invalid:5432/justi_innov
REDIS_URL=redis://redis-de-production.invalid:6379/0
EMAIL_HOST=smtp-de-production.invalid
SENTRY_DSN=https://cle@sentry-de-production.invalid/1
SUPERVISION=1
EOF

# docker : à l'appel qui démarrerait la pile, Compose écrit la configuration
# résolue, puis le script s'arrête là. Le reste ne touche à rien.
cat > "$BAC/bin/docker" <<EOF
#!/bin/sh
case "\$*" in
  "compose up"*) "$REEL" compose config --format json > "$BAC/config.json"; exit 1 ;;
esac
exit 0
EOF
chmod +x "$BAC/bin/docker"

(
  export COMPOSE_PROJECT_NAME=justi-innov COMPOSE_FILE=docker-compose.prod.yml
  export DATABASE_URL=postgresql://justi_app:x@base-du-shell.invalid:5432/justi_innov
  cd "$BAC/exploitation"
  HOME="$BAC/maison" PATH="$BAC/bin:$PATH" \
    sh ./repeter_la_restauration.sh justi_innov-2026-11-18T020000Z.dump --compte ci </dev/null >/dev/null 2>&1 || true
)
[ -s "$BAC/config.json" ] || { echo "✘ Compose n'a rien résolu" >&2; exit 1; }

python3 - "$BAC/config.json" <<'PY'
import json
import sys

config = json.load(open(sys.argv[1]))
echecs = []


def verifier(condition, message):
    print(f"  {'✔' if condition else '✘'} {message}")
    if not condition:
        echecs.append(message)


services = config["services"]
verifier(config["name"] == "justi-restauration", f"projet jetable ({config['name']})")
verifier(not services["caddy"].get("ports"), "Caddy ne publie aucun port")
volumes = [v.get("name", "") for v in config.get("volumes", {}).values()]
verifier(volumes and all(v.startswith("justi-restauration_") for v in volumes),
         "chaque volume est celui du projet jetable")
verifier(not {"grafana", "grafana-bi", "prometheus"} & set(services), "ni supervision ni BI")
texte = json.dumps(config)
for hote in ("base-de-production", "base-du-shell", "redis-de-production",
             "smtp-de-production", "sentry-de-production"):
    verifier(hote not in texte, f"rien ne mène à {hote}")
for nom in ("backend", "scheduler"):
    env = services[nom]["environment"]
    verifier(env.get("EMAIL_BACKEND_CONSOLE") == "1", f"{nom} : courrier en console")
    verifier(env.get("REDIS_URL") == "redis://redis:6379/0", f"{nom} : le Redis de la pile")
    verifier(not env.get("DATABASE_URL"), f"{nom} : la base de la pile")
verifier(services["sauvegarde"]["environment"].get("PGHOST") == "db"
         and not services["sauvegarde"]["environment"].get("DATABASE_URL"),
         "la restauration écrit dans la base de la pile")
print(f"\n{len(echecs)} échec(s).")
sys.exit(1 if echecs else 0)
PY
