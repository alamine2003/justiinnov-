#!/bin/sh
# Restaure une sauvegarde faite par sauvegarder.sh, depuis le volume
# `sauvegardes` de la pile.
#
#   ./restaurer.sh --lister                       # les dumps disponibles
#   ./restaurer.sh justi_innov-2026-09-04T020000Z.dump
#                                                 # restaure la base de la pile
#   ./restaurer.sh mensuel/justi_innov-2026-09.dump
#                                                 # depuis une copie mensuelle
#   ./restaurer.sh <dump> --base test_restauration
#                                                 # dans une base jetable, pour
#                                                 # le test trimestriel
#   ./restaurer.sh --pieces                       # remet le miroir des
#                                                 # justificatifs dans le bucket
#
# Restaurer la base de la pile arrête le backend et l'ordonnanceur le temps
# de l'opération, puis les relance. `pg_restore --clean --if-exists` supprime
# chaque objet avant de le recréer : ce qui a été écrit depuis le dump est
# perdu, d'où la confirmation demandée. Le rôle applicatif est ensuite
# rétabli (creer_role_applicatif.sql, s'il est en service).
set -eu

cd "$(dirname "$0")"

compose() {
  docker compose -f docker-compose.prod.yml "$@"
}

# Un shell dans le service `sauvegarde` : il voit le volume et la base, et
# porte les variables PG* de connexion. `-T` : pas de terminal, pour pouvoir
# enchaîner dans un script.
dans_sauvegarde() {
  compose run --rm -T --entrypoint sh sauvegarde -c "$1"
}

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

[ $# -ge 1 ] || usage

if [ ! -f .env ]; then
  echo "✘ Aucun fichier .env dans $(pwd)." >&2
  exit 1
fi

# Lecture de .env sans l'exécuter : les cadences cron qu'il contient
# (`0 * * * *`) feraient des dégâts dans un `source`. Dernière occurrence,
# guillemets simples ou doubles retirés.
valeur() {
  grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e "s/^'\(.*\)'\$/\1/" -e 's/^"\(.*\)"$/\1/'
}
POSTGRES_DB="$(valeur POSTGRES_DB)"
POSTGRES_USER="$(valeur POSTGRES_USER)"
POSTGRES_PASSWORD="$(valeur POSTGRES_PASSWORD)"
POSTGRES_MIGRATION_USER="$(valeur POSTGRES_MIGRATION_USER)"
# Valeurs par défaut identiques à celles de docker-compose.prod.yml.
base_pile="${POSTGRES_DB:-justi_innov}"
proprietaire="${POSTGRES_MIGRATION_USER:-${POSTGRES_USER:-justi}}"

case "$1" in
  --lister)
    echo "Dumps quotidiens (gardés SAUVEGARDE_RETENTION_JOURS jours) :"
    dans_sauvegarde 'ls -lhp /sauvegardes/base/ 2>/dev/null | grep -v "/$" || echo "(aucun)"'
    echo "Copies mensuelles (conservées sans limite), à désigner par mensuel/<nom> :"
    dans_sauvegarde 'ls -lh /sauvegardes/base/mensuel/ 2>/dev/null || echo "(aucune)"'
    exit 0
    ;;
  --pieces)
    echo "→ Restauration des justificatifs depuis le miroir vers le bucket…"
    compose run --rm -T --entrypoint sh sauvegarde-pieces -c '
      set -eu
      export MC_CONFIG_DIR=/tmp/mc
      mc --quiet alias set pile "${AWS_S3_ENDPOINT_URL:-http://minio:9000}" "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY" >/dev/null
      mc mb --ignore-existing "pile/${AWS_STORAGE_BUCKET_NAME:-justificatifs}"
      mc mirror --overwrite /sauvegardes/pieces "pile/${AWS_STORAGE_BUCKET_NAME:-justificatifs}"
    '
    echo "✔ Justificatifs restaurés."
    exit 0
    ;;
  --*)
    usage
    ;;
esac

dump="$1"
shift
base_cible="$base_pile"
if [ "${1:-}" = "--base" ]; then
  base_cible="${2:?nom de la base après --base}"
  shift 2
fi
[ $# -eq 0 ] || usage

case "$dump" in
  mensuel/*) ;;
  */*) echo "✘ Donnez le nom du dump tel que listé par --lister (ou mensuel/<nom>), sans autre chemin." >&2; exit 1 ;;
esac

if ! dans_sauvegarde "test -f '/sauvegardes/base/$dump'"; then
  echo "✘ Dump introuvable dans le volume : $dump (voir --lister)." >&2
  exit 1
fi

if [ "$base_cible" = "$base_pile" ]; then
  echo "⚠ Cette restauration ÉCRASE la base « $base_pile » de la pile avec le"
  echo "  contenu de $dump. Tout ce qui a été saisi depuis est perdu."
  printf "  Pour continuer, tapez le nom de la base : "
  read -r confirmation
  if [ "$confirmation" != "$base_pile" ]; then
    echo "Abandon." >&2
    exit 1
  fi
  echo "→ Arrêt du backend et de l'ordonnanceur…"
  compose stop backend scheduler
else
  echo "→ Création de la base jetable « $base_cible » (si absente)…"
  dans_sauvegarde "psql -d postgres -tAc \"SELECT 1 FROM pg_database WHERE datname = '$base_cible'\" | grep -q 1 \
    || psql -d postgres -c 'CREATE DATABASE \"$base_cible\" OWNER \"$proprietaire\"'"
fi

echo "→ Restauration de $dump dans « $base_cible »…"
# --no-owner --no-privileges : tout appartient au rôle qui restaure (le
# propriétaire) ; les droits du rôle applicatif sont rejoués juste après,
# plutôt que dépendre de ce que le dump en dit.
dans_sauvegarde "pg_restore --clean --if-exists --no-owner --no-privileges \
  --dbname '$base_cible' '/sauvegardes/base/$dump'"

echo "→ Contenu restauré :"
dans_sauvegarde "psql -d '$base_cible' -tAc \"SELECT '  tables : ' || count(*) FROM pg_tables WHERE schemaname = 'public'\""
for table in expenses_expense expenses_proof expenses_auditlog; do
  dans_sauvegarde "psql -d '$base_cible' -tAc \"SELECT '  $table : ' || count(*) FROM $table\"" 2>/dev/null \
    || echo "  $table : absente (dump antérieur à cette table ?)"
done
dans_sauvegarde "psql -d '$base_cible' -tAc \"SELECT '  dernière entrée du journal d''audit : ' || coalesce(max(created_at)::text, 'aucune') FROM expenses_auditlog\"" 2>/dev/null || true

if [ -n "${POSTGRES_MIGRATION_USER:-}" ]; then
  echo "→ Droits du rôle applicatif « ${POSTGRES_USER:-justi_app} » sur « $base_cible »…"
  dans_sauvegarde "psql -d '$base_cible' -v ON_ERROR_STOP=1 \
    -v role_applicatif='${POSTGRES_USER:-justi_app}' \
    -v mot_de_passe='${POSTGRES_PASSWORD:-}' -f /creer_role_applicatif.sql"
fi

if [ "$base_cible" = "$base_pile" ]; then
  echo "→ Relance du backend et de l'ordonnanceur…"
  compose up -d --wait backend scheduler
  echo "✔ Base restaurée depuis $dump ; la pile est en ligne."
else
  echo "✔ Base « $base_cible » restaurée depuis $dump."
  echo "  Quand vous avez fini de la vérifier :"
  echo "  docker compose -f docker-compose.prod.yml exec db dropdb -U $proprietaire $base_cible"
fi
