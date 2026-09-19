#!/bin/sh
# Prépare la seconde machine : copie initiale de la base, puis attente chaude.
#
#   ./preparer_replique.sh --primaire <hôte> [--emplacement <nom>]
#
# À lancer **sur la seconde machine**, une fois. Elle en ressort réplique :
# elle rejoue le flux de la primaire en continu et se laisse interroger en
# lecture — c'est ce que veut dire « attente chaude », et c'est ce qui
# permet de vérifier qu'elle suit au lieu de l'espérer.
#
# AVANT DE LANCER, SUR LA PRIMAIRE :
#   1. le rôle de réplication existe (creer_role_replication.sql) ;
#   2. `pg_hba.conf` accepte son adresse — et **seulement** la sienne ;
#   3. le port 5432 de la primaire est joignable depuis ici, par un réseau
#      privé ou un tunnel. **Jamais par l'Internet en clair** : un flux de
#      réplication, c'est la base entière, jetons de session et secrets TOTP
#      compris.
#
# CE QU'IL FAUT AVOIR EN TÊTE
#
#   Une réplique n'est pas une sauvegarde. Un `DELETE` malheureux se
#   réplique en moins d'une milliseconde. La réplique protège de la perte
#   d'une machine ; l'archivage des journaux (décision 74) protège de
#   l'erreur humaine. Il faut les deux, ils ne se remplacent pas.
#
#   La réplication est **asynchrone**. Une transaction validée sur la
#   primaire qui meurt avant d'avoir envoyé son journal est perdue. C'est un
#   choix : en synchrone, chaque écriture attendrait la seconde machine, et
#   une réplique absente **bloquerait toute la plateforme** — un remède pire
#   que le mal quand il n'y a qu'une réplique.
#
# MESURÉ SUR BANC (deux grappes locales, lien sans latence) : retard de
# réplication 0 octet / 0,69 ms, copie initiale d'une base de 15 Mo en
# 0,5 s, promotion en 0,11 s, aucune perte après un SIGKILL de la primaire.
# Sur deux machines réelles, le retard suit l'aller-retour du réseau.

set -eu

PRIMAIRE=""
EMPLACEMENT="replique"
UTILISATEUR="${POSTGRES_REPLICATION_USER:-replicateur}"
PORT_PRIMAIRE="${POSTGRES_REPLICATION_PORT:-5432}"
REPERTOIRE="${PGDATA:-/var/lib/postgresql/data}"

journal() { echo "$(date -u +%FT%TZ) réplique $*"; }
echec() { echo "$(date -u +%FT%TZ) réplique ✘ $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --primaire) PRIMAIRE="${2:?hôte attendu après --primaire}"; shift 2 ;;
    --emplacement) EMPLACEMENT="${2:?nom attendu après --emplacement}"; shift 2 ;;
    --port) PORT_PRIMAIRE="${2:?port attendu après --port}"; shift 2 ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    *) echec "option inconnue : $1 (voir --help)" ;;
  esac
done

[ -n "$PRIMAIRE" ] || echec "il faut dire qui suivre : --primaire <hôte>"
[ -n "${PGPASSWORD:-}" ] || echec "PGPASSWORD (mot de passe du rôle de réplication) est vide"

# Un répertoire déjà peuplé serait écrasé : on refuse plutôt que de détruire
# ce qui pourrait être la seule copie restante.
if [ -s "$REPERTOIRE/PG_VERSION" ]; then
  echec "$REPERTOIRE contient déjà une base. Si c'est une ancienne réplique à refaire, effacez-la sciemment d'abord."
fi

journal "vérification du lien vers $PRIMAIRE:$PORT_PRIMAIRE…"
pg_isready -h "$PRIMAIRE" -p "$PORT_PRIMAIRE" -t 10 >/dev/null \
  || echec "$PRIMAIRE:$PORT_PRIMAIRE ne répond pas. Réseau, pare-feu, ou pg_hba.conf ?"

journal "copie initiale depuis $PRIMAIRE (emplacement « $EMPLACEMENT »)…"
debut="$(date +%s)"
# -R écrit `primary_conninfo` et `standby.signal` : la réplique sait alors
#    qui suivre, sans qu'on ait à composer le fichier à la main.
# --slot --create-slot : l'emplacement demande à la primaire de garder ce que
#    nous n'avons pas encore lu. C'est ce qui évite un trou pendant une
#    coupure de réseau — et ce que `max_slot_wal_keep_size` borne sur la
#    primaire, pour qu'une réplique absente ne remplisse jamais son disque.
pg_basebackup \
  --host "$PRIMAIRE" --port "$PORT_PRIMAIRE" --username "$UTILISATEUR" \
  --pgdata "$REPERTOIRE" --format=plain --wal-method=stream \
  --checkpoint=fast --write-recovery-conf \
  --slot="$EMPLACEMENT" --create-slot --progress --no-password \
  || echec "copie initiale impossible : la réplique n'est pas en place"
duree=$(( $(date +%s) - debut ))

chmod 700 "$REPERTOIRE"
journal "✔ copie faite en ${duree}s ($(du -sh "$REPERTOIRE" | cut -f1))"

grep -q "primary_conninfo" "$REPERTOIRE/postgresql.auto.conf" \
  || echec "primary_conninfo absent : la base démarrerait en primaire, pas en réplique"
[ -f "$REPERTOIRE/standby.signal" ] \
  || echec "standby.signal absent : la base démarrerait en primaire, pas en réplique"

cat <<'FIN'

  La base est prête à suivre. Démarrez la pile de cette machine :

    docker compose -f docker-compose.prod.yml -f docker-compose.replique.yml up -d

  Puis vérifiez, DEPUIS LA PRIMAIRE, qu'elle suit vraiment :

    docker compose -f docker-compose.prod.yml exec db \
      psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
      -c "select application_name, state, sync_state, replay_lag from pg_stat_replication"

  « state = streaming » veut dire qu'elle suit. Tant que cette ligne
  n'apparaît pas, il n'y a pas de réplique — seulement une copie qui vieillit.

FIN
