#!/bin/sh
# Tests de `repeter_la_restauration.sh` (décision 131), sans Docker, sans
# réseau : `docker` est une doublure qui note chaque appel et le répertoire
# d'où il part ; `restaurer.sh` est le vrai, lancé par le script.
#
#   deploy/tests/test_repeter_la_restauration.sh
#
# Ce qui compte, et ne se découvrirait sinon que sur le serveur de
# production : **aucune commande ne part du répertoire d'exploitation**, son
# .env n'est jamais modifié, une étape en échec ne passe jamais pour
# réussie, et la clé saisie ne finit ni dans le .env de la production ni
# dans le compte rendu.
set -eu

ICI="$(cd "$(dirname "$0")" && pwd)"
DEPLOY="$ICI/.."

BAC="$(mktemp -d)"
trap 'rm -rf "$BAC"' EXIT
DOUBLURES="$BAC/bin"
mkdir -p "$DOUBLURES"
PATH="$DOUBLURES:$PATH"
export PATH

reussis=0
echecs=0
compte() { grep -c "$@" 2>/dev/null || true; }
verifier() {
  if [ "$2" = "$3" ]; then
    reussis=$((reussis + 1))
    printf '  ✔ %s\n' "$1"
  else
    echecs=$((echecs + 1))
    printf '  ✘ %s\n     attendu : %s\n     obtenu  : %s\n' "$1" "$3" "$2" >&2
  fi
}

# --- Doublure de docker --------------------------------------------------------
#
# Une ligne par appel dans $APPELS : « <répertoire>|<projet du .env de ce
# répertoire>|<arguments> ». Codes et sorties réglables par l'environnement.
cat > "$DOUBLURES/docker" <<'EOF'
#!/bin/sh
projet="$(grep -E '^COMPOSE_PROJECT_NAME=' .env 2>/dev/null | tail -1 | cut -d= -f2-)"
# Un appel par ligne : les scripts passés à `sh -c` tiennent sur plusieurs.
echo "$(pwd -P)|${projet:--}|$(printf '%s' "$*" | tr '\n' ' ')" >> "$APPELS"
case "$*" in
  "volume ls"*) printf '%s' "${VOLUMES_EXISTANTS:-}"; exit 0 ;;
  *" up -d --wait db minio backend"*) echo "pile démarrée"; exit "${CODE_UP:-0}" ;;
  *verifier_restauration*) echo "Pièces vérifiées : 12 sur 12"; exit "${CODE_VERIFIER:-0}" ;;
  *mesurer_les_temps*) echo "Tableau de bord   p50 1100.0 ms"; exit 0 ;;
  *"wc -c"*) echo "4242"; exit 0 ;;
esac
exit 0
EOF
chmod +x "$DOUBLURES/docker"

# --- Un répertoire d'exploitation ----------------------------------------------

EXPLOITATION="$BAC/justi-innov"
mkdir -p "$EXPLOITATION/initdb" "$EXPLOITATION/caddy"
cp "$DEPLOY/repeter_la_restauration.sh" "$DEPLOY/restaurer.sh" "$EXPLOITATION/"
for f in docker-compose.prod.yml sauvegarder.sh restaurer_a_la_date.sh archiver_wal.sh \
         creer_role_applicatif.sql creer_role_bi.sql Caddyfile; do
  echo "# $f" > "$EXPLOITATION/$f"
done
echo "-- pg_hba" > "$EXPLOITATION/initdb/10-replication.sh"
cat > "$EXPLOITATION/.env" <<'EOF'
POSTGRES_DB=justi_innov
POSTGRES_USER=justi
EMAIL_HOST=smtp.exemple.invalid
SAUVEGARDE_DISTANT_ENDPOINT=https://exemple.r2.cloudflarestorage.com
SAUVEGARDE_CHIFFREMENT_CLE=cle-du-serveur
SUPERVISION=1
EOF
EMPREINTE_ENV="$(cksum < "$EXPLOITATION/.env")"

export HOME="$BAC/maison"
mkdir -p "$HOME"
DOSSIER="$HOME/restauration"
RAPPORTS="$HOME/comptes-rendus-de-restauration"
APPELS="$BAC/appels"
export APPELS
DUMP=justi_innov-2026-11-18T020000Z.dump

lancer() {
  : > "$APPELS"
  code=0
  (cd "$BAC" && "$EXPLOITATION/repeter_la_restauration.sh" "$@") > "$BAC/sortie" 2>&1 < "${ENTREE:-/dev/null}" || code=$?
}
rapport() { ls "$RAPPORTS"/restauration-*.md 2>/dev/null | tail -1; }
detruire() { rm -rf "$DOSSIER" "$RAPPORTS"; }

echo "Arguments"
lancer "$DUMP"
verifier "sans --compte : refus" "$code" "1"
verifier "sans --compte : aucune pile créée" "$([ -e "$DOSSIER" ] && echo oui || echo non)" "non"
lancer "x';rm -rf /;'.dump" --compte rh.essai
verifier "un nom de dump hors alphabet est refusé" "$code" "1"
verifier "… sans appeler docker" "$(wc -l < "$APPELS" | tr -d ' ')" "0"
VOLUMES_EXISTANTS="justi-restauration_pgdata" lancer "$DUMP" --compte rh.essai
verifier "des volumes jetables restés d'une répétition : refus" "$code" "1"

echo "Répétition complète"
lancer "$DUMP" --compte rh.essai
verifier "sortie en succès" "$code" "0"
DOSSIER_REEL="$(cd "$DOSSIER" && pwd -P)"
verifier "chaque commande compose part de la pile jetable" \
  "$(grep -v '|volume ls' "$APPELS" | compte -v "^$DOSSIER_REEL|justi-restauration|")" "0"
verifier "aucune commande ne part du répertoire d'exploitation" \
  "$(compte "^$(cd "$EXPLOITATION" && pwd -P)|" "$APPELS")" "0"
verifier "le .env de la production est intact" "$(cksum < "$EXPLOITATION/.env")" "$EMPREINTE_ENV"
verifier "projet jetable" "$(grep -c '^COMPOSE_PROJECT_NAME=justi-restauration$' "$DOSSIER/.env")" "1"
verifier "courrier en console" "$(grep -c '^EMAIL_BACKEND_CONSOLE=1$' "$DOSSIER/.env")" "1"
verifier "aucun serveur de courrier" "$(compte 'smtp.exemple.invalid' "$DOSSIER/.env")" "0"
verifier "ni supervision ni profils" "$(compte -E '^(SUPERVISION|COMPOSE_PROFILES)=' "$DOSSIER/.env")" "0"
verifier "aucun port public pour caddy" "$(compte 'ports: \[\]' "$DOSSIER/docker-compose.override.yml")" "1"
verifier "initdb et archiver_wal.sh copiés (montés par la base)" \
  "$([ -f "$DOSSIER/initdb/10-replication.sh" ] && [ -f "$DOSSIER/archiver_wal.sh" ] && echo oui)" "oui"
verifier "rapatriement du dump depuis le distant" "$(compte "sauvegarde-distante --rapatrier $DUMP" "$APPELS")" "1"
verifier "restaurer.sh a eu sa confirmation et a restauré" "$(compte 'pg_restore --clean' "$APPELS")" "1"
verifier "pièces rapatriées puis restaurées" "$(compte 'sauvegarde-distante --rapatrier-pieces' "$APPELS")" "1"
verifier "mesure avec le compte donné, sur base jetable" \
  "$(compte 'mesurer_les_temps --base-jetable --compte rh.essai' "$APPELS")" "1"
verifier "les services de sauvegarde ne sont jamais démarrés" "$(compte -E 'up .*sauvegarde' "$APPELS")" "0"
RAPPORT="$(rapport)"
verifier "compte rendu écrit hors de la pile" "$([ -f "$RAPPORT" ] && echo oui)" "oui"
verifier "verdict : réussie" "$(compte 'Verdict | réussie' "$RAPPORT")" "1"
verifier "cinq étapes chronométrées" "$(compte -E '^\| [0-9]' "$RAPPORT")" "5"
verifier "taille du dump" "$(compte "$DUMP\` (4242 octets)" "$RAPPORT")" "1"
verifier "sortie de verifier_restauration gardée" "$(compte 'Pièces vérifiées : 12 sur 12' "$RAPPORT")" "1"
verifier "clé : celle du serveur, dit tel quel" "$(compte 'celle du .env du serveur' "$RAPPORT")" "1"

echo "Une seconde répétition sans --detruire"
lancer "$DUMP" --compte rh.essai
verifier "refus : la pile précédente est encore là" "$code" "1"

echo "--detruire"
cp "$DOSSIER/.env" "$BAC/env-jetable"
sed -i 's/^COMPOSE_PROJECT_NAME=.*/COMPOSE_PROJECT_NAME=justi-innov/' "$DOSSIER/.env"
lancer --detruire
verifier "un .env qui ne nomme pas le projet jetable : refus" "$code" "1"
verifier "… et aucun down" "$(compte 'down' "$APPELS")" "0"
cp "$BAC/env-jetable" "$DOSSIER/.env"
lancer --detruire
verifier "destruction acceptée" "$code" "0"
verifier "down -v depuis la pile jetable" "$(compte "^$DOSSIER_REEL|justi-restauration|compose down -v" "$APPELS")" "1"
verifier "le dossier jetable a disparu" "$([ -e "$DOSSIER" ] && echo oui || echo non)" "non"
verifier "le compte rendu survit" "$([ -f "$RAPPORT" ] && echo oui)" "oui"
detruire

echo "Une vérification en échec"
CODE_VERIFIER=3 lancer "$DUMP" --compte rh.essai
verifier "sortie en échec" "$code" "1"
RAPPORT="$(rapport)"
verifier "verdict : échouée à la vérification" "$(compte 'échouée à l.étape « 3. verifier_restauration »' "$RAPPORT")" "1"
verifier "rien n'est mesuré après l'échec" "$(compte 'mesurer_les_temps' "$APPELS")" "0"
detruire

echo "Une pile qui ne démarre pas"
CODE_UP=1 lancer "$DUMP" --compte rh.essai
verifier "sortie en échec" "$code" "1"
verifier "verdict : échouée à l'étape 1" "$(compte 'échouée à l.étape « 1. Pile jetable en ligne »' "$(rapport)")" "1"
verifier "rien n'est restauré" "$(compte 'pg_restore' "$APPELS")" "0"
detruire

echo "--cle-hors-serveur"
printf 'cle-du-coffre\n' > "$BAC/entree"
ENTREE="$BAC/entree" lancer "$DUMP" --compte rh.essai --cle-hors-serveur
verifier "sortie en succès" "$code" "0"
verifier "la pile jetable rapatrie avec la clé saisie" \
  "$(grep -c '^SAUVEGARDE_CHIFFREMENT_CLE=cle-du-coffre$' "$DOSSIER/.env")" "1"
verifier "… et elle seule" "$(grep -c '^SAUVEGARDE_CHIFFREMENT_CLE=' "$DOSSIER/.env")" "1"
verifier "le .env de la production est intact" "$(cksum < "$EXPLOITATION/.env")" "$EMPREINTE_ENV"
verifier "la clé n'est pas dans le compte rendu" "$(compte 'cle-du-coffre' "$(rapport)")" "0"
verifier "la clé n'est pas affichée" "$(compte 'cle-du-coffre' "$BAC/sortie")" "0"
verifier "le compte rendu dit quelle clé a servi" "$(compte 'copie gardée hors du serveur' "$(rapport)")" "1"
detruire

echo
echo "$reussis vérification(s) réussie(s), $echecs en échec."
[ "$echecs" -eq 0 ]
