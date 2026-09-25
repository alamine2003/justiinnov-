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
# Il tourne dans le service `reprise` de docker-compose.prod.yml — le seul,
# avec la base, qui voie le répertoire de données — et sous l'utilisateur
# `postgres`, le seul que `pg_ctl` accepte :
#
#   docker compose -f docker-compose.prod.yml run --rm reprise \
#     --a '2026-09-19 14:31:00+00'
#
#   --a <instant>      instant visé, lu par Postgres (recovery_target_time).
#                      Tout format qu'il accepte : « 2026-09-19 14:31:00+00 ».
#   --essai            (défaut) restaure dans un répertoire jetable, ouvre
#                      une base temporaire dans ce conteneur, dit où elle
#                      s'est arrêtée, compte ce qu'elle contient, exécute
#                      --requete s'il y en a une, puis la jette.
#                      **La production n'est pas touchée.** C'est ce mode
#                      qu'on répète tous les trimestres, et c'est le seul
#                      qui soit sans risque.
#   --requete <sql>    en --essai : une requête à exécuter sur la base
#                      rejouée avant de la jeter, par exemple
#                      "select count(*) from expenses_expense".
#   --en-production    remplace le répertoire de données de la pile.
#                      Destructif, demande une confirmation tapée à la main,
#                      et exige que la base soit arrêtée
#                      (`docker compose stop db backend scheduler`).
#   --port <n>         port de la base d'essai (5499 par défaut).
#   --depuis <horodatage>
#                      nomme la sauvegarde physique de départ, quand le
#                      script ne sait pas la choisir seul (date illisible).
#
# CE QUI A ÉTÉ ÉPROUVÉ. Le mécanisme — sauvegarde physique, segments
# rejoués, arrêt à l'instant voulu — a été mesuré sur un banc de 72 Mo
# pendant l'audit de résilience : 3,0 s pour la sauvegarde physique, 0,6 s
# pour la reprise, les lignes effacées par erreur retrouvées et la bêtise
# absente. La chaîne complète dans la pile livrée — archivage par la base,
# sauvegarde physique par le service, reprise par ce script dans son
# conteneur — est rejouée par l'intégration continue (travail « Pile de
# production ») à chaque changement. Le mode --en-production, lui, touche
# la pile réelle : il se répète d'abord en --essai, sur ce serveur, avant
# d'être cru.

set -eu

INSTANT=""
DEPUIS=""
MODE="essai"
PORT="5499"
REQUETE=""
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
    --requete) REQUETE="${2:?requête attendue après --requete}"; shift 2 ;;
    --depuis) DEPUIS="${2:?horodatage attendu après --depuis}"; shift 2 ;;
    -h|--help) sed -n '2,50p' "$0"; exit 0 ;;
    *) echec "option inconnue : $1 (voir --help)" ;;
  esac
done

[ -n "$INSTANT" ] || echec "il faut dire jusqu'où rejouer : --a '2026-09-19 14:31:00+00'"

# `pg_ctl` refuse root, et un répertoire de données créé par root ne serait
# pas lisible par la base. Le service `reprise` tourne sous `postgres` ;
# lancé autrement, on le dit plutôt que d'échouer plus loin.
[ "$(id -u)" -ne 0 ] || echec "ne pas lancer en root : « docker compose run --rm reprise … » tourne sous postgres"

PHYSIQUES="$DESTINATION/base/physique"
ARCHIVE="$DESTINATION/base/wal"

[ -d "$PHYSIQUES" ] || echec "aucune sauvegarde physique dans $PHYSIQUES : la reprise à un instant donné est impossible. Un dump ne peut pas en tenir lieu."
[ -d "$ARCHIVE" ] || echec "aucun segment archivé dans $ARCHIVE : il n'y a rien à rejouer."

# La sauvegarde physique la plus récente qui PRÉCÈDE l'instant visé : partir
# d'une plus récente que la cible rendrait la reprise impossible — Postgres
# refuse de remonter le temps, et le dirait par une erreur obscure.
#
# Sans `date -d` : c'est une extension GNU que le BusyBox de l'image Alpine
# n'a pas, et la CI l'a vu à sa première exécution — le script demandait
# --depuis à chaque fois. On compare des chaînes : le nom d'une sauvegarde
# est « 2026-09-19T020000Z », l'instant est ramené à la même forme compacte
# « 20260919020000 » dès qu'il est écrit en UTC (suffixe +00, +0000,
# +00:00, Z, ou sans décalage — Postgres lit alors l'heure du serveur, qui
# est UTC dans la pile). Un instant dans un autre fuseau n'est pas deviné :
# l'exploitant nomme le point de départ.
compact_utc() {
  # "2026-09-19 14:31:00.123+00" → "20260919143100" ; vide si pas en UTC.
  printf '%s' "$1" | sed -n -E \
    's/^([0-9]{4})-([0-9]{2})-([0-9]{2})[T ]([0-9]{2}):([0-9]{2})(:([0-9]{2}))?(\.[0-9]+)?[[:space:]]*(Z|\+00(:?00)?|UTC)?$/\1\2\3\4\5\7/p' \
    | sed -E 's/^([0-9]{12})$/\100/'
}

choisir_le_point_de_depart() {
  if [ -n "$DEPUIS" ]; then
    [ -d "$PHYSIQUES/$DEPUIS" ] || echec "sauvegarde physique inconnue : $DEPUIS (voir $PHYSIQUES)"
    echo "$PHYSIQUES/$DEPUIS/"
    return 0
  fi
  instant_compact="$(compact_utc "$INSTANT")"
  if [ -z "$instant_compact" ]; then
    echo "" ; return 0
  fi
  trouvee=""
  for candidate in "$PHYSIQUES"/*/; do
    [ -d "$candidate" ] || continue
    nom="$(basename "$candidate")"
    # 2026-09-19T020000Z → 20260919020000 ; un nom d'une autre forme est ignoré.
    quand="$(printf '%s' "$nom" | sed -n -E 's/^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{6})Z$/\1\2\3\4/p')"
    [ -n "$quand" ] || continue
    # Deux nombres de quatorze chiffres : la comparaison numérique est POSIX.
    if [ "$quand" -le "$instant_compact" ]; then
      trouvee="$candidate"
    fi
  done
  echo "$trouvee"
}

choisie="$(choisir_le_point_de_depart)"
if [ -z "$choisie" ]; then
  echo "Sauvegardes physiques disponibles :" >&2
  ls -1 "$PHYSIQUES" >&2 2>/dev/null || true
  echec "impossible de choisir seul le point de départ (instant hors UTC ou illisible, ou aucune sauvegarde antérieure à $INSTANT). Nommez-le : --depuis <horodatage>"
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
  # mal, il reste la seule chose qui contienne encore les données. Il ne
  # peut pas être renommé : c'est un point de montage (le volume `pgdata`),
  # et le noyau refuse. Son contenu part donc, élément par élément, dans le
  # volume des sauvegardes — le même disque, un déplacement, pas une copie.
  sauvegarde_du_repertoire="$DESTINATION/base/avant-reprise-$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$sauvegarde_du_repertoire" && chmod 700 "$sauvegarde_du_repertoire" \
    || echec "impossible de créer $sauvegarde_du_repertoire"
  for element in "$cible"/* "$cible"/.[!.]*; do
    [ -e "$element" ] || continue
    mv "$element" "$sauvegarde_du_repertoire"/ \
      || echec "impossible de mettre $element de côté : le répertoire de données est dans un état mixte, ne relancez pas la pile avant d'avoir compris"
  done
  journal "ancien répertoire conservé : $sauvegarde_du_repertoire (à effacer une fois la reprise vérifiée)"
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
  pg_ctl -D "$cible" -o "-p $PORT -c listen_addresses=localhost" -l "$cible/reprise.log" -w start \
    || { tail -20 "$cible/reprise.log" >&2; echec "la base d'essai n'a pas démarré"; }
  base="${PGDATABASE:-justi_innov}"
  requete() { psql -h localhost -p "$PORT" -d "$base" -v ON_ERROR_STOP=1 -qtAX -c "$1"; }
  jeter_l_essai() { pg_ctl -D "$cible" -m fast -w stop >/dev/null 2>&1 || true; rm -rf "$cible"; }
  # `pg_ctl -w` rend la main dès que la base accepte des connexions — en
  # reprise, c'est AVANT la fin du rejeu : la première répétition sur le
  # serveur (25 septembre 2026) lisait la base au milieu du rejeu et
  # concluait « ✔ » sur une reprise inachevée, voire morte. La reprise
  # n'est finie que lorsque la base s'ouvre en écriture
  # (`recovery_target_action = 'promote'`) ; on l'attend, ou l'on constate
  # que Postgres s'est arrêté, et l'on dit pourquoi.
  attente="${REPRISE_ATTENTE_SECONDES:-600}"
  debut="$(date +%s)"
  while :; do
    ecoule=$(( $(date +%s) - debut ))
    if ! pg_ctl -D "$cible" status >/dev/null 2>&1; then
      tail -20 "$cible/reprise.log" >&2
      if grep -q 'recovery ended before configured recovery target was reached' "$cible/reprise.log"; then
        rm -rf "$cible"
        echec "aucune transaction validée après $INSTANT dans l'archive : Postgres a tout rejoué sans trouver où s'arrêter, et s'est arrêté plutôt que d'ouvrir une base d'état incertain. Si la base est restée sans écriture depuis, validez une transaction vide après l'instant visé (« select txid_current() »), forcez l'archivage (« select pg_switch_wal() ») et recommencez ; sinon, l'archive s'arrête avant $INSTANT (deploy/README.md, « Répéter la reprise »)."
      fi
      rm -rf "$cible"
      echec "la base d'essai s'est arrêtée pendant le rejeu (journal ci-dessus)"
    fi
    [ "$(requete 'select not pg_is_in_recovery()' 2>/dev/null || true)" = "t" ] && break
    if [ "$ecoule" -ge "$attente" ]; then
      tail -20 "$cible/reprise.log" >&2
      jeter_l_essai
      echec "le rejeu n'a pas fini en $attente s (REPRISE_ATTENTE_SECONDES) : la base est-elle plus grosse que prévu ? (journal ci-dessus)"
    fi
    sleep 1
  done
  echo ""
  journal "✔ base d'essai ouverte, à l'instant $INSTANT (rejeu terminé en ${ecoule} s)"
  # Là où Postgres s'est arrêté : la ligne du journal qui le dit, mot pour
  # mot. « recovery stopping before commit of transaction … time … » est
  # l'instant exact.
  arret="$(grep -E 'recovery stopping (before|after|at)' "$cible/reprise.log" | tail -1 || true)"
  if [ -n "$arret" ]; then
    echo "    arrêt : ${arret#*LOG:  }"
  else
    jeter_l_essai
    echec "la base s'est ouverte sans dire où elle s'est arrêtée : reprise non conforme, rien n'est prouvé"
  fi
  echo "    en écriture : t"
  # Ce que la base contient, pour comparer avec la production sans
  # deviner : les tables qui font la valeur de la plateforme.
  for table in expenses_dossier expenses_expense expenses_proof budget_budget accounts_profile; do
    if compte="$(requete "select count(*) from $table" 2>/dev/null)"; then
      echo "    $table : $compte ligne(s)"
    fi
  done
  if [ -n "$REQUETE" ]; then
    echo ""
    echo "    résultat de --requete :"
    # Pas de tube : le statut de `sed` masquait celui de la requête, et
    # une requête en échec finissait sur « ✔ ».
    if ! resultat="$(requete "$REQUETE")"; then
      jeter_l_essai
      echec "la requête a échoué"
    fi
    printf '%s\n' "$resultat" | sed 's/^/      /'
  fi
  echo ""
  jeter_l_essai
  journal "✔ base d'essai jetée. La pile n'a pas été touchée."
else
  journal "✔ répertoire de données remplacé. Relancez la pile :"
  echo "    docker compose -f docker-compose.prod.yml up -d"
  echo ""
  echo "    Postgres rejouera les segments au démarrage, puis s'ouvrira."
  echo "    Vérifiez les données AVANT d'effacer $sauvegarde_du_repertoire."
fi
