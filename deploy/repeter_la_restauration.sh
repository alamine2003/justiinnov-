#!/bin/sh
# Répète la restauration dans un environnement isolé, la chronomètre et en
# écrit le compte rendu daté (README.md, « Restauration dans un environnement
# isolé » ; décision 131).
#
#   ./repeter_la_restauration.sh <dump> --compte <identifiant> [--cle-hors-serveur]
#                                       # étapes 1 à 3 bis, compte rendu daté
#   ./repeter_la_restauration.sh --detruire
#                                       # étape 5 : la pile jetable, volumes compris
#
#   <dump>              nom tel que le liste ./restaurer.sh --lister (copie
#                       hors machine), par exemple justi_innov-2026-11-18T020000Z.dump
#   --compte            un compte administrateur du dump, pour mesurer_les_temps
#   --cle-hors-serveur  demande (sans l'afficher) la copie de la clé de
#                       chiffrement gardée hors du serveur, et rapatrie avec
#                       elle : c'est ce qui prouve qu'elle déchiffre le coffre
#
# À lancer depuis le répertoire d'exploitation (là où vivent .env,
# docker-compose.prod.yml et restaurer.sh). Rien n'y est écrit : la pile
# jetable vit dans RESTAURATION_DOSSIER (~/restauration par défaut), sous le
# projet Compose « justi-restauration », avec ses propres volumes, le courrier
# en console et aucun port public. Le compte rendu va dans
# RESTAURATION_RAPPORTS (~/comptes-rendus-de-restauration), hors de la pile,
# qu'il survive à --detruire.
#
# L'étape 4 (ouvrir l'application restaurée par un tunnel) reste à la main :
# la pile est laissée en marche pour elle, et le script dit comment la
# détruire ensuite.
set -eu

PROJET=justi-restauration
SOURCE="$(cd "$(dirname "$0")" && pwd)"
DOSSIER="${RESTAURATION_DOSSIER:-$HOME/restauration}"
RAPPORTS="${RESTAURATION_RAPPORTS:-$HOME/comptes-rendus-de-restauration}"

# Ce que docker-compose.prod.yml monte depuis le répertoire : sans l'un
# d'eux, Docker crée un répertoire vide à sa place et le service démarre
# de travers (l'archivage de la base appelle archiver_wal.sh).
FICHIERS="docker-compose.prod.yml sauvegarder.sh restaurer.sh restaurer_a_la_date.sh
archiver_wal.sh creer_role_applicatif.sql creer_role_bi.sql Caddyfile"
REPERTOIRES="initdb caddy"

usage() {
  sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

refuser() { echo "✘ $1" >&2; exit 1; }

# Dernière valeur d'une clé dans un .env, sans l'exécuter (même lecture que
# restaurer.sh : les cadences cron d'un `source` feraient des dégâts).
valeur() {
  grep -E "^$1=" "$2" 2>/dev/null | tail -1 | cut -d= -f2- \
    | sed -e "s/^'\(.*\)'\$/\1/" -e 's/^"\(.*\)"$/\1/'
}

# Le seul verrou qui compte : chaque commande Docker de ce script part du
# dossier jetable, dont le .env nomme le projet jetable — jamais celui de la
# production. Vérifié avant chaque étape, pas une fois au début.
exiger_l_isolement() {
  [ -f "$DOSSIER/.env" ] || refuser "$DOSSIER/.env absent : ce n'est pas une pile jetable."
  [ "$(valeur COMPOSE_PROJECT_NAME "$DOSSIER/.env")" = "$PROJET" ] \
    || refuser "$DOSSIER/.env ne nomme pas le projet « $PROJET » : rien n'est lancé."
  dossier_reel="$(cd "$DOSSIER" && pwd -P)"
  source_reelle="$(cd "$SOURCE" && pwd -P)"
  [ "$dossier_reel" != "$source_reelle" ] \
    || refuser "le dossier jetable est le répertoire d'exploitation : rien n'est lancé."
  projet_source="$(valeur COMPOSE_PROJECT_NAME "$SOURCE/.env")"
  [ "${projet_source:-$(basename "$source_reelle")}" != "$PROJET" ] \
    || refuser "le répertoire d'exploitation porte lui-même le projet « $PROJET »."
}

compose_isole() {
  exiger_l_isolement
  (cd "$DOSSIER" && docker compose "$@")
}

# --- --detruire ----------------------------------------------------------------

if [ "${1:-}" = "--detruire" ]; then
  [ $# -eq 1 ] || usage
  [ -d "$DOSSIER" ] || refuser "aucune pile jetable dans $DOSSIER."
  exiger_l_isolement
  echo "→ Arrêt de la pile « $PROJET » et retrait de ses volumes…"
  compose_isole down -v
  rm -rf "$DOSSIER"
  echo "✔ Pile jetable détruite. Le compte rendu reste dans $RAPPORTS."
  exit 0
fi

# --- Arguments -----------------------------------------------------------------

[ $# -ge 1 ] || usage
case "$1" in -*) usage ;; esac
DUMP="$1"
shift
COMPTE=""
CLE_HORS_SERVEUR=0
while [ $# -gt 0 ]; do
  case "$1" in
    --compte) COMPTE="${2:-}"; [ -n "$COMPTE" ] || usage; shift 2 ;;
    --cle-hors-serveur) CLE_HORS_SERVEUR=1; shift ;;
    *) usage ;;
  esac
done
[ -n "$COMPTE" ] || refuser "--compte <identifiant> manque : un compte administrateur du dump, pour mesurer les temps."
# Un nom de quotidien (justi_innov-2026-11-18T020000Z.dump) : il finit dans
# une commande du conteneur, d'où l'alphabet borné.
case "$DUMP" in
  *[!A-Za-z0-9._-]*|'') refuser "donnez le nom du dump tel que le liste ./restaurer.sh --lister, sans chemin." ;;
esac

[ -f "$SOURCE/.env" ] || refuser "aucun .env dans $SOURCE : lancez le script depuis le répertoire d'exploitation."
[ -n "$(valeur SAUVEGARDE_DISTANT_ENDPOINT "$SOURCE/.env")" ] \
  || refuser "aucune copie hors machine configurée (SAUVEGARDE_DISTANT_ENDPOINT) : il n'y a rien à rapatrier."
[ ! -e "$DOSSIER" ] \
  || refuser "$DOSSIER existe déjà : une répétition précédente n'a pas été détruite (./repeter_la_restauration.sh --detruire)."
if [ -n "$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJET")" ]; then
  refuser "des volumes du projet « $PROJET » existent encore : retirez-les d'abord (docker volume ls --filter label=com.docker.compose.project=$PROJET)."
fi
for f in $FICHIERS restaurer.sh; do
  [ -f "$SOURCE/$f" ] || refuser "$SOURCE/$f manque : le répertoire d'exploitation est-il à jour ?"
done
for d in $REPERTOIRES; do
  [ -d "$SOURCE/$d" ] || refuser "$SOURCE/$d/ manque : le répertoire d'exploitation est-il à jour ?"
done

CLE=""
if [ "$CLE_HORS_SERVEUR" -eq 1 ]; then
  printf 'Clé de chiffrement, la copie gardée hors du serveur (masquée) : ' >&2
  stty -echo 2>/dev/null || true
  IFS= read -r CLE || true
  stty echo 2>/dev/null || true
  printf '\n' >&2
  [ -n "$CLE" ] || refuser "clé vide : rien n'est lancé."
fi

# --- Le compte rendu -----------------------------------------------------------

mkdir -p "$RAPPORTS"
HORODATAGE="$(date -u +%Y-%m-%dT%H%M%SZ)"
RAPPORT="$RAPPORTS/restauration-$HORODATAGE.md"
JOURNAUX="$(mktemp -d)"
trap 'rm -rf "$JOURNAUX"' EXIT
DEBUT_TOTAL="$(date +%s)"
RESUME=""
DETAILS=""

duree() {
  s="$1"
  if [ "$s" -ge 60 ]; then printf '%d min %02d s' $((s / 60)) $((s % 60)); else printf '%d s' "$s"; fi
}

ecrire_le_rapport() {
  verdict="$1"
  {
    echo "# Restauration isolée du $(date -u +%Y-%m-%d)"
    echo
    echo "| | |"
    echo "|---|---|"
    echo "| Verdict | $verdict |"
    echo "| Serveur | $(hostname) |"
    echo "| Début (UTC) | $HORODATAGE |"
    echo "| Dump | \`$DUMP\`${TAILLE:+ ($TAILLE octets)} |"
    if [ "$CLE_HORS_SERVEUR" -eq 1 ]; then
      echo "| Clé de chiffrement | la copie gardée hors du serveur, saisie à la main |"
    else
      echo "| Clé de chiffrement | celle du .env du serveur (pas la copie hors serveur) |"
    fi
    echo "| Compte de mesure | \`$COMPTE\` |"
    echo "| Durée totale | $(duree $(( $(date +%s) - DEBUT_TOTAL ))) |"
    echo
    echo "## Étapes"
    echo
    echo "| Étape | Durée | Résultat |"
    echo "|---|---|---|"
    printf '%b' "$RESUME"
    echo
    echo "Délai de reprise mesuré : la somme des étapes 1 et 2 (pile en ligne,"
    echo "base et pièces restaurées depuis le distant), à comparer aux 4 h de"
    echo "l'objectif (README.md, « Objectifs »)."
    echo
    echo "## Sorties"
    printf '%b' "$DETAILS"
    echo
    echo "## À compléter à la main"
    echo
    echo "- Étape 4 : connexion, un dossier justifié pris au hasard, sa pièce ouverte —"
    echo "  fait le … par …"
    echo "- Décomptes comparés à ceux de la production au moment du dump :"
    echo "- Écarts constatés, limites restantes :"
  } > "$RAPPORT"
}

# etape <titre> <commande> [arguments…] : chronomètre, garde la sortie, et
# arrête tout au premier échec — compte rendu écrit, verdict « échouée ».
etape() {
  titre="$1"
  shift
  journal="$JOURNAUX/$(printf '%s' "$titre" | tr -c 'a-zA-Z0-9' '_')"
  echo
  echo "=== $titre"
  debut="$(date +%s)"
  # L'étape tourne dans un sous-shell sous `set -e` (hors de toute
  # condition, où `-e` serait ignoré) : sa première commande en échec,
  # ou un refus, l'arrête, et son code est noté avant que le tuyau ne
  # se referme — une étape interrompue ne passe jamais pour réussie.
  { set +e; ( set -e; "$@" ) 2>&1; echo "$?" > "$journal.code"; } | tee "$journal"
  code="$(cat "$journal.code" 2>/dev/null || echo 1)"
  ecoule=$(( $(date +%s) - debut ))
  if [ "$code" -eq 0 ]; then resultat="réussie"; else resultat="**échec (code $code)**"; fi
  RESUME="${RESUME}| $titre | $(duree "$ecoule") | $resultat |\n"
  DETAILS="${DETAILS}\n### $titre\n\n\`\`\`\n$(sed 's/\\/\\\\/g' "$journal")\n\`\`\`\n"
  if [ "$code" -ne 0 ]; then
    ecrire_le_rapport "échouée à l'étape « $titre »"
    echo
    echo "✘ Échec à l'étape « $titre ». Compte rendu : $RAPPORT"
    echo "  La pile jetable reste en place pour l'enquête ; ./repeter_la_restauration.sh --detruire la retire."
    exit 1
  fi
}

# --- 1. La pile jetable --------------------------------------------------------

preparer_la_pile() {
  mkdir -p "$DOSSIER"
  for f in $FICHIERS; do cp -p "$SOURCE/$f" "$DOSSIER/$f"; done
  for d in $REPERTOIRES; do cp -Rp "$SOURCE/$d" "$DOSSIER/$d"; done
  # Mêmes images (BACKEND_IMAGE, FRONTEND_IMAGE, IMAGE_TAG, écrits par
  # deploy.sh), autre projet donc autres volumes, courrier en console,
  # aucun port public, aucun profil (ni supervision ni BI).
  grep -v -E '^(EMAIL_BACKEND_CONSOLE|EMAIL_HOST|COMPOSE_PROJECT_NAME|COMPOSE_FILE|COMPOSE_PROFILES|SUPERVISION)=' \
    "$SOURCE/.env" > "$DOSSIER/.env"
  cat >> "$DOSSIER/.env" <<EOF
EMAIL_HOST=
EMAIL_BACKEND_CONSOLE=1
COMPOSE_PROJECT_NAME=$PROJET
COMPOSE_FILE=docker-compose.prod.yml:docker-compose.override.yml
EOF
  if [ -n "$CLE" ]; then
    # La valeur voyage par l'environnement d'awk : ni dans la ligne de
    # commande (ps), ni dans un programme interprété.
    CLE_SAISIE="$CLE" awk 'index($0, "SAUVEGARDE_CHIFFREMENT_CLE=") == 1 { next } { print } END { print "SAUVEGARDE_CHIFFREMENT_CLE=" ENVIRON["CLE_SAISIE"] }' \
      "$DOSSIER/.env" > "$DOSSIER/.env.nouveau"
    mv "$DOSSIER/.env.nouveau" "$DOSSIER/.env"
  fi
  chmod 600 "$DOSSIER/.env"
  cat > "$DOSSIER/docker-compose.override.yml" <<'EOF'
services:
  caddy:
    ports: []            # rien n'écoute sur Internet
EOF
  exiger_l_isolement
  # Les services de sauvegarde ne sont pas démarrés : rien ne repart vers le
  # distant depuis cette pile.
  compose_isole up -d --wait db minio backend
}

etape "1. Pile jetable en ligne" preparer_la_pile
CLE=""

# --- 2. Rapatrier et restaurer, depuis le distant ------------------------------

BASE="$(valeur POSTGRES_DB "$DOSSIER/.env")"
BASE="${BASE:-justi_innov}"

restaurer_la_base() {
  exiger_l_isolement
  # restaurer.sh demande le nom de la base avant d'écraser : c'est la base
  # du projet jetable, vérifié juste au-dessus, d'où la réponse donnée ici.
  printf '%s\n' "$BASE" | (cd "$DOSSIER" && ./restaurer.sh --depuis-distant "$DUMP")
}
restaurer_les_pieces() {
  exiger_l_isolement
  (cd "$DOSSIER" && ./restaurer.sh --depuis-distant --pieces)
}

etape "2a. Base rapatriée et restaurée" restaurer_la_base
TAILLE="$(compose_isole run --rm -T --entrypoint sh sauvegarde -c "wc -c < '/sauvegardes/base/$DUMP'" 2>/dev/null | tr -dc '0-9' || true)"
etape "2b. Justificatifs rapatriés et restaurés" restaurer_les_pieces

# --- 3. Vérifier, 3 bis. Mesurer -----------------------------------------------

etape "3. verifier_restauration" compose_isole exec -T backend python manage.py verifier_restauration
etape "3 bis. mesurer_les_temps" compose_isole exec -T backend python manage.py mesurer_les_temps \
  --base-jetable --compte "$COMPTE" --repetitions 20 --simultanes 4

ecrire_le_rapport "réussie (étapes 1 à 3 bis)"
cat <<FIN

✔ Restauration répétée. Compte rendu : $RAPPORT

Reste à la main :
  4. Ouvrir l'application restaurée par un tunnel (README.md, étape 4),
     puis compléter la fin du compte rendu.
  5. Détruire la pile jetable : ./repeter_la_restauration.sh --detruire
  6. Ranger le compte rendu dans le journal d'exploitation.
FIN
