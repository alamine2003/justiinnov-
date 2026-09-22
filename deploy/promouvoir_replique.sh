#!/bin/sh
# Bascule : la réplique devient la primaire, et l'application démarre ici.
#
#   ./promouvoir_replique.sh --primaire-perdue <hôte>
#   ./promouvoir_replique.sh --primaire-perdue <hôte> --repetition
#
# À lancer **sur la seconde machine**, quand la première est perdue.
#
# LA RÉPLICATION N'EST PAS LA PARTIE DIFFICILE. Elle marche toute seule et
# se mesure. Ce qui rate, le jour venu, c'est la bascule : on promeut la
# base et on oublie que le domaine pointe toujours ailleurs ; ou l'on
# promeut alors que la primaire vivait encore, et deux bases acceptent des
# écritures que plus rien ne réconciliera. Ce script s'occupe de ce qu'une
# machine peut faire, et **dit en toutes lettres** ce qui reste à une
# personne.
#
# CE QU'IL FAIT
#   1. refuse de promouvoir si la primaire répond encore ;
#   2. promeut la base (elle passe en écriture, et se met à archiver) ;
#   3. démarre l'application, l'ordonnanceur et les sauvegardes ici ;
#   4. rappelle les deux gestes qui restent : le domaine, et l'ancienne
#      machine qu'on ne redémarre pas.
#
# --repetition joue tout sauf la promotion : c'est la répétition
# trimestrielle, celle qui fait qu'on sait quoi taper le jour où les mains
# tremblent.

set -eu

PRIMAIRE=""
REPETITION=0
COMPOSE="${COMPOSE_FILE:-docker-compose.prod.yml:docker-compose.replique.yml}"
PORT_PRIMAIRE="${POSTGRES_REPLICATION_PORT:-5432}"

journal() { echo "$(date -u +%FT%TZ) bascule $*"; }
echec() { echo "$(date -u +%FT%TZ) bascule ✘ $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --primaire-perdue) PRIMAIRE="${2:?hôte attendu}"; shift 2 ;;
    --repetition) REPETITION=1; shift ;;
    --port) PORT_PRIMAIRE="${2:?port attendu}"; shift 2 ;;
    -h|--help) sed -n '2,32p' "$0"; exit 0 ;;
    *) echec "option inconnue : $1 (voir --help)" ;;
  esac
done

[ -n "$PRIMAIRE" ] || echec "nommez la machine perdue : --primaire-perdue <hôte>"

compose() { docker compose -f docker-compose.prod.yml -f docker-compose.replique.yml "$@"; }

# --- 1. Garde-fou contre deux primaires ---------------------------------------
#
# C'est la vérification la plus importante du script. Deux bases qui
# acceptent des écritures produisent deux histoires, et rien ne les
# réconcilie : il faudra en jeter une, avec ce qu'elle contient.
# `pg_isready` vit dans l'image de la base, pas sur l'hôte : on l'y appelle.
# La réplique tourne déjà, c'est ce qu'elle est.
journal "la primaire $PRIMAIRE répond-elle encore ?"
if compose exec -T db pg_isready -h "$PRIMAIRE" -p "$PORT_PRIMAIRE" -t 5 >/dev/null 2>&1; then
  echo "" >&2
  echo "  ⚠ $PRIMAIRE RÉPOND ENCORE." >&2
  echo "    Promouvoir maintenant donnerait deux bases qui acceptent des" >&2
  echo "    écritures, et deux histoires qu'on ne pourra plus réunir." >&2
  echo "" >&2
  echo "    Si la primaire est vraiment à remplacer, arrêtez-la d'abord," >&2
  echo "    pour de bon :" >&2
  echo "      ssh $PRIMAIRE 'cd ~/justi-innov && docker compose -f docker-compose.prod.yml down'" >&2
  echo "" >&2
  echec "bascule refusée tant que l'ancienne primaire vit"
fi
journal "✔ $PRIMAIRE ne répond pas"

if [ "$REPETITION" -eq 1 ]; then
  journal "répétition : la base n'est PAS promue, rien n'est irréversible"
else
  # --- 2. Promotion -----------------------------------------------------------
  journal "promotion de la base…"
  debut="$(date +%s)"
  # `pg_promote()` plutôt que la promotion par pg_ctl : `exec` entre dans le
  # conteneur en root, et `pg_ctl` refuse root. La fonction SQL, elle,
  # s'exécute dans le serveur, attend (60 s au plus) que la bascule soit
  # faite, et rend `t` — ou `f`, qui est un échec, pas une attente.
  promue="$(compose exec -T db psql -qtAX -U "${POSTGRES_USER:-justi}" \
              -d "${POSTGRES_DB:-justi_innov}" -c 'select pg_promote(true, 60)' 2>&1 | tr -d ' ')"
  [ "$promue" = "t" ] \
    || echec "la promotion a échoué (pg_promote → ${promue:-rien}) : regardez « docker compose logs db »"
  # Postgres rend la main dès que la bascule est faite ; on vérifie qu'elle
  # accepte vraiment les écritures plutôt que de le supposer.
  attente=0
  while [ "$attente" -lt 30 ]; do
    if [ "$(compose exec -T db psql -qtAX -U "${POSTGRES_USER:-justi}" \
              -d "${POSTGRES_DB:-justi_innov}" -c 'select pg_is_in_recovery()' 2>/dev/null | tr -d ' ')" = "f" ]; then
      break
    fi
    attente=$((attente + 1)); sleep 1
  done
  [ "$attente" -lt 30 ] || echec "la base est promue mais reste en lecture seule : n'allez pas plus loin"
  journal "✔ base en écriture après $(( $(date +%s) - debut ))s ; l'archivage des journaux démarre de lui-même"
fi

# --- 3. L'application démarre ici ---------------------------------------------
journal "démarrage de l'application, de l'ordonnanceur et des sauvegardes…"
compose --profile bascule up -d --wait \
  || echec "des services n'ont pas démarré : « docker compose ps » puis les journaux"
journal "✔ pile en service sur cette machine"

# --- 4. Ce qui reste à une personne -------------------------------------------
cat <<FIN

  ───────────────────────────────────────────────────────────────────────
  LA BASE ET L'APPLICATION TOURNENT ICI. DEUX GESTES RESTENT, ET AUCUN
  SCRIPT NE PEUT LES FAIRE À VOTRE PLACE.

  1. LE TRAFIC DOIT ARRIVER ICI.

     AVEC UN AIGUILLAGE (docker-compose.balanceur.yml) : rien à faire.
     Il interroge /api/health/ toutes les cinq secondes, voit que cette
     machine accepte désormais les écritures, et bascule seul. Mesuré sur un
     banc à deux machines : service rétabli 4,8 s après le démarrage de
     l'application ici. Vérifiez-le plutôt que de le supposer :
       curl -sS https://<le domaine>/api/health/

     SANS AIGUILLAGE : LE DOMAINE POINTE ENCORE SUR $PRIMAIRE.
     Tant qu'il n'est pas changé, personne n'arrive ici : la bascule est
     faite pour les machines, pas pour les gens. Changez l'enregistrement
     A vers l'adresse de cette machine-ci, et rappelez-vous que le cache
     DNS met le temps de son TTL à s'effacer — c'est là que passe
     l'essentiel du temps d'indisponibilité réel, et c'est précisément ce
     qu'un aiguillage supprime.

  2. NE REDÉMARREZ JAMAIS $PRIMAIRE EN PRIMAIRE.
     C'EST LE SEUL POINT QUI N'EST PROTÉGÉ PAR AUCUN PROGRAMME.

     Ses données s'arrêtent à l'instant de sa perte ; les vôtres ont
     continué. Rallumée telle quelle, elle n'est pas en récupération : elle
     accepte les écritures, /api/health/ y répond 200 en toute sincérité, et
     l'aiguillage — qui préfère toujours la première machine — lui rend le
     trafic. Mesuré sur un banc à deux machines : le trafic y est revenu
     5,1 s après son retour, et 22 des 24 requêtes suivantes ont été servies
     par la base périmée. Deux histoires, et rien pour les réunir.

     L'AIGUILLAGE AGGRAVE CE CAS AU LIEU DE LE COUVRIR : sans lui, il faut
     qu'une personne rebascule le DNS ; avec lui, le retour est automatique.

     Donc, tant que $PRIMAIRE n'est pas refaite en réplique : qu'elle reste
     éteinte. Si elle peut redémarrer seule (redémarrage de l'hôte,
     « restart: unless-stopped »), empêchez-la avant qu'elle ne le fasse :
       ssh $PRIMAIRE 'cd ~/justi-innov && docker compose -f docker-compose.prod.yml down'
     puis, quand vous êtes prêt à la remettre en service, sur elle :
       docker compose -f docker-compose.prod.yml -f docker-compose.replique.yml \\
         run --rm -e PGPASSWORD='…' --entrypoint /preparer_replique.sh db --primaire <cette machine>

  Et vérifiez ce qui tourne :
     docker compose -f docker-compose.prod.yml -f docker-compose.replique.yml ps
     curl -sS -o /dev/null -w '%{http_code}\\n' http://localhost:8080/api/health/
  ───────────────────────────────────────────────────────────────────────

FIN
