#!/bin/sh
# Reprise de la base à un instant donné (PITR).
#
# Le dump quotidien dit où l'on était à 02:00. Les segments archivés
# (archiver_wal.sh) disent tout ce qui s'est passé depuis. Ce script
# assemble les deux : une sauvegarde physique comme point de départ, les
# segments rejoués jusqu'à l'instant demandé — pas plus loin.
#
# À quoi cela sert, concrètement :
#   - une panne de disque à 01:59 ne perd plus la journée, mais quelques
#     minutes ;
#   - un effacement par erreur à 14:32 se répare en repartant de 14:31,
#     ce qu'aucun dump quotidien ne permet.
#
#   docker compose -f docker-compose.prod.yml run --rm --entrypoint \
#     /restaurer_a_la_date.sh sauvegarde --a '2026-09-19 14:31:00+00'
#
#   --a <instant>      instant visé, lu par Postgres (recovery_target_time).
#                      Tout format qu'il accepte : « 2026-09-19 14:31:00+00 ».
#   --essai            (défaut) restaure dans un répertoire jetable et
#                      démarre une base temporaire sur --port : on regarde,
#                      on compare, on jette. **La production n'est pas
#                      touchée.** C'est ce mode qu'on répète tous les
#                      trimestres, et c'est le seul qui soit sans risque.
#   --en-production    remplace le répertoire de données de la pile. Destructif,
#                      demande une confirmation tapée à la main, et exige que
#                      la base soit arrêtée (`docker compose stop db backend
#                      scheduler`).
#   --port <n>         port de la base d'essai (5499 par défaut).
#   --depuis <horodatage>
#                      nomme la sauvegarde physique de départ, quand le
#                      script ne sait pas la choisir seul (date illisible).
#
# CE QUI A ÉTÉ ÉPROUVÉ. Le mécanisme — sauvegarde physique, segments
# rejoués, arrêt à l'instant voulu — a été mesuré sur un banc de 72 Mo
# pendant l'audit de résilience : 3,0 s pour la sauvegarde physique, 0,6 s
# pour la reprise, les lignes effacées par erreur retrouvées et la bêtise
# absente. Le mode --en-production, lui, touche la pile réelle : il se
# répète d'abord en --essai, sur ce serveur, avant d'être cru.

set -eu

INSTANT=""
DEPUIS=""
MODE="essai"
PORT="5499"
DESTINATION="${SAUVEGARDE_DESTINATION:-/sauvegardes}"
CLE_PRIVEE="${SAUVEGARDE_CLE_PRIVEE:-}"
SUFFIXE_CHIFFRE=".enc"
REPERTOIRE_PRODUCTION="${PGDATA:-/var/lib/postgresql/data}"

journal() { echo "$(date -u +%FT%TZ) reprise $*"; }
echec() { echo "$(date -u +%FT%TZ) reprise ✘ $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --a) INSTANT="${2:?instant attendu après --a}"; shift 2 ;;
    --essai) MODE="essai"; shift ;;
    --en-production) MODE="production"; shift ;;
    --port) PORT="${2:?port attendu après --port}"; shift 2 ;;
    --depuis) DEPUIS="${2:?horodatage attendu après --depuis}"; shift 2 ;;
    -h|--help) sed -n '2,34p' "$0"; exit 0 ;;
    *) echec "option inconnue : $1 (voir --help)" ;;
  esac
done

[ -n "$INSTANT" ] || echec "il faut dire jusqu'où rejouer : --a '2026-09-19 14:31:00+00'"

PHYSIQUES="$DESTINATION/base/physique"
ARCHIVE="$DESTINATION/base/wal"

[ -d "$PHYSIQUES" ] || echec "aucune sauvegarde physique dans $PHYSIQUES : la reprise à un instant donné est impossible. Un dump ne peut pas en tenir lieu."
[ -d "$ARCHIVE" ] || echec "aucun segment archivé dans $ARCHIVE : il n'y a rien à rejouer."

# La sauvegarde physique la plus récente qui PRÉCÈDE l'instant visé : partir
# d'une plus récente que la cible rendrait la reprise impossible — Postgres
# refuse de remonter le temps, et le dirait par une erreur obscure.
#
# `date -d` est une extension GNU ; le BusyBox de l'image Alpine ne la
# comprend pas toujours. Plutôt que de deviner et de choisir mal, on
# demande alors à l'exploitant de nommer le point de départ.
choisir_le_point_de_depart() {
  if [ -n "$DEPUIS" ]; then
    [ -d "$PHYSIQUES/$DEPUIS" ] || echec "sauvegarde physique inconnue : $DEPUIS (voir $PHYSIQUES)"
    echo "$PHYSIQUES/$DEPUIS/"
    return 0
  fi
  instant_epoch="$(date -u -d "$INSTANT" +%s 2>/dev/null || echo "")"
  if [ -z "$instant_epoch" ]; then
    echo "" ; return 0
  fi
  trouvee=""
  for candidate in "$PHYSIQUES"/*/; do
    [ -d "$candidate" ] || continue
    # L'horodatage est dans le nom : 2026-09-19T020000Z
    nom="$(basename "$candidate")"
    quand="$(echo "$nom" | sed 's/T\([0-9][0-9]\)\([0-9][0-9]\)\([0-9][0-9]\)Z/ \1:\2:\3+00/')"
    quand_epoch="$(date -u -d "$quand" +%s 2>/dev/null || echo 0)"
    if [ "$quand_epoch" -ne 0 ] && [ "$quand_epoch" -le "$instant_epoch" ]; then
      trouvee="$candidate"
    fi
  done
  echo "$trouvee"
}

choisie="$(choisir_le_point_de_depart)"
if [ -z "$choisie" ]; then
  echo "Sauvegardes physiques disponibles :" >&2
  ls -1 "$PHYSIQUES" >&2 2>/dev/null || true
  echec "impossible de choisir seul le point de départ (date illisible, ou aucune sauvegarde antérieure à $INSTANT). Nommez-le : --depuis <horodatage>"
fi
journal "point de départ : $choisie"

# La commande que Postgres appellera pour chaque segment. Chiffrée, elle
# passe par openssl ; en clair, c'est une copie.
if ls "$ARCHIVE"/*"$SUFFIXE_CHIFFRE" >/dev/null 2>&1; then
  [ -n "$CLE_PRIVEE" ] || echec "les segments sont chiffrés et SAUVEGARDE_CLE_PRIVEE est vide : la clé privée est hors du serveur, apportez-la (README.md, « Chiffrement »)."
  [ -s "$CLE_PRIVEE" ] || echec "SAUVEGARDE_CLE_PRIVEE=$CLE_PRIVEE introuvable ou vide"
  COMMANDE_DE_REPRISE="openssl smime -decrypt -binary -inform DER -inkey $CLE_PRIVEE -in $ARCHIVE/%f$SUFFIXE_CHIFFRE -out %p"
else
  COMMANDE_DE_REPRISE="cp $ARCHIVE/%f %p"
fi

if [ "$MODE" = "production" ]; then
  cible="$REPERTOIRE_PRODUCTION"
  if [ -s "$cible/postmaster.pid" ]; then
    echec "la base tourne encore : arrêtez-la d'abord (docker compose stop db backend scheduler)"
  fi
  echo ""
  echo "  ⚠ CECI REMPLACE LE RÉPERTOIRE DE DONNÉES DE LA PILE."
  echo "    Tout ce qui a été écrit après $INSTANT sera perdu."
  echo "    Répétez d'abord en --essai si ce n'est pas fait."
  echo ""
  printf "    Tapez « remplacer » pour continuer : "
  read -r reponse
  [ "$reponse" = "remplacer" ] || echec "annulé — rien n'a été touché"
  # Le répertoire actuel est mis de côté, pas effacé : si la reprise tourne
  # mal, il reste la seule chose qui contienne encore les données.
  sauvegarde_du_repertoire="$cible.avant-reprise-$(date -u +%Y%m%dT%H%M%SZ)"
  mv "$cible" "$sauvegarde_du_repertoire" \
    || echec "impossible de mettre l'ancien répertoire de côté"
  journal "ancien répertoire conservé : $sauvegarde_du_repertoire (à effacer une fois la reprise vérifiée)"
  mkdir -p "$cible"
else
  cible="${SAUVEGARDE_REPRISE_ESSAI:-/tmp/reprise-essai}"
  rm -rf "$cible"
  mkdir -p "$cible"
fi

chmod 700 "$cible"
journal "dépliage de la sauvegarde physique…"
tar -xzf "$choisie/base.tar.gz" -C "$cible" || echec "dépliage impossible"

cat >> "$cible/postgresql.auto.conf" <<EOF

# Reprise à un instant donné, posée par restaurer_a_la_date.sh
restore_command = '$COMMANDE_DE_REPRISE'
recovery_target_time = '$INSTANT'
# Une fois l'instant atteint, la base s'ouvre en écriture. Sans cela elle
# resterait en lecture seule et l'on croirait la reprise ratée.
recovery_target_action = 'promote'
# L'archivage est coupé le temps de la reprise : une base qui rejoue ne doit
# pas réécrire par-dessus l'archive dont elle se sert.
archive_mode = off
EOF
touch "$cible/recovery.signal"

if [ "$MODE" = "essai" ]; then
  journal "démarrage de la base d'essai sur le port $PORT…"
  pg_ctl -D "$cible" -o "-p $PORT" -l "$cible/reprise.log" -w start \
    || { tail -20 "$cible/reprise.log" >&2; echec "la base d'essai n'a pas démarré"; }
  echo ""
  journal "✔ base d'essai ouverte sur le port $PORT, à l'instant $INSTANT"
  echo "    Regardez-la :   psql -p $PORT -d ${PGDATABASE:-justi_innov} -c 'select count(*) from expenses_expense'"
  echo "    Jetez-la :      pg_ctl -D $cible -m immediate stop && rm -rf $cible"
  echo ""
  echo "    La pile n'a pas été touchée."
else
  journal "✔ répertoire de données remplacé. Relancez la pile :"
  echo "    docker compose -f docker-compose.prod.yml up -d"
  echo ""
  echo "    Postgres rejouera les segments au démarrage, puis s'ouvrira."
  echo "    Vérifiez les données AVANT d'effacer $sauvegarde_du_repertoire."
fi
