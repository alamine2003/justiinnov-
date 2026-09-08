#!/bin/sh
# Tests de `sauvegarder.sh`, exécutables partout où il y a un shell POSIX et
# openssl — sans PostgreSQL, sans MinIO, sans réseau.
#
#   deploy/tests/test_sauvegarder.sh
#
# Le script de sauvegarde n'appelle que quatre programmes extérieurs :
# `pg_dump`, `mc`, `rclone` et `openssl`. Les trois premiers sont remplacés
# ici par des doublures qui écrivent ce qu'on leur demande d'écrire et
# rendent le code de sortie qu'on leur demande de rendre ; `openssl` est le
# vrai, parce que c'est lui qu'on veut vérifier. On peut ainsi éprouver ce
# qui compte vraiment et qui, autrement, ne se découvre qu'une nuit de
# panne : **qu'une sauvegarde ratée ne se signale jamais comme réussie**.
#
# La CI l'exécute (`ci.yml`, travail « Exploitation ») ; en local, il ne
# touche qu'un répertoire temporaire, qu'il efface en sortant.
set -eu

ICI="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$ICI/../sauvegarder.sh"
[ -f "$SCRIPT" ] || { echo "✘ sauvegarder.sh introuvable à côté de tests/" >&2; exit 2; }

BAC="$(mktemp -d)"
trap 'rm -rf "$BAC"' EXIT
DOUBLURES="$BAC/bin"
mkdir -p "$DOUBLURES"
PATH="$DOUBLURES:$PATH"
export PATH

reussis=0
echecs=0

# `grep -c` écrit « 0 » **et** sort en 1 quand il ne trouve rien : un
# `|| echo 0` derrière en écrirait un second. Cette fonction rend le seul
# décompte.
compte() { grep -c "$@" 2>/dev/null || true; }

verifier_au_moins_une_fois() {
  if [ "${2:-0}" -ge 1 ]; then
    reussis=$((reussis + 1))
    printf '  ✔ %s\n' "$1"
  else
    echecs=$((echecs + 1))
    printf '  ✘ %s\n     attendu : au moins une occurrence\n     obtenu  : %s\n' "$1" "${2:-0}" >&2
  fi
}

verifier() {
  if [ "$2" = "$3" ]; then
    reussis=$((reussis + 1))
    printf '  ✔ %s\n' "$1"
  else
    echecs=$((echecs + 1))
    printf '  ✘ %s\n     attendu : %s\n     obtenu  : %s\n' "$1" "$3" "$2" >&2
  fi
}

# --- Doublures ----------------------------------------------------------------
#
# `pg_dump` : écrit CONTENU_DUMP dans le fichier de `--file`, ou sur la
# sortie standard, et sort avec CODE_PGDUMP.

cat > "$DOUBLURES/pg_dump" <<'DOUBLURE'
#!/bin/sh
sortie=""
suivant=0
for arg in "$@"; do
  if [ "$suivant" = 1 ]; then sortie="$arg"; suivant=0; fi
  [ "$arg" = "--file" ] && suivant=1
done
contenu="${CONTENU_DUMP-PGDMP-faux-dump}"
if [ -n "$sortie" ]; then
  printf '%s' "$contenu" > "$sortie"
else
  printf '%s' "$contenu"
fi
exit "${CODE_PGDUMP:-0}"
DOUBLURE

cat > "$DOUBLURES/mc" <<'DOUBLURE'
#!/bin/sh
for arg in "$@"; do
  if [ "$arg" = "mirror" ]; then
    dest=""
    for a in "$@"; do dest="$a"; done
    mkdir -p "$dest" && printf 'faux-justificatif' > "$dest/recu.pdf"
  fi
done
exit "${CODE_MC:-0}"
DOUBLURE

# `rclone` : journalise chaque appel dans $BAC/rclone.log et rend CODE_RCLONE
# (ou CODE_RCLONE_CHECK pour `check`/`cryptcheck`, pour simuler une copie
# arrivée corrompue).
cat > "$DOUBLURES/rclone" <<'DOUBLURE'
#!/bin/sh
echo "$*" >> "${JOURNAL_RCLONE:-/dev/null}"
case "${1:-}" in
  obscure) printf 'obscurci-%s' "${2:-}" ; exit 0 ;;
  check|cryptcheck) exit "${CODE_RCLONE_CHECK:-0}" ;;
esac
exit "${CODE_RCLONE:-0}"
DOUBLURE

chmod +x "$DOUBLURES/pg_dump" "$DOUBLURES/mc" "$DOUBLURES/rclone"

# --- Décor --------------------------------------------------------------------

decor() {
  DESTINATION="$BAC/sauvegardes-$1"
  rm -rf "$DESTINATION"
  mkdir -p "$DESTINATION"
  JOURNAL_RCLONE="$BAC/rclone-$1.log"
  : > "$JOURNAL_RCLONE"
  export SAUVEGARDE_DESTINATION="$DESTINATION" JOURNAL_RCLONE
  unset CODE_PGDUMP CONTENU_DUMP CODE_MC CODE_RCLONE CODE_RCLONE_CHECK 2>/dev/null || true
  unset SAUVEGARDE_CLE_PUBLIQUE SAUVEGARDE_DISTANT_ENDPOINT SAUVEGARDE_CHIFFREMENT_CLE 2>/dev/null || true
  unset SAUVEGARDE_DISTANT_BUCKET SAUVEGARDE_DISTANT_CLE SAUVEGARDE_DISTANT_SECRET 2>/dev/null || true
  unset SAUVEGARDE_DISTANT_ROTATION SAUVEGARDE_DISTANT_EN_CLAIR 2>/dev/null || true
  export PGDATABASE=justi_innov
}

lancer() {
  # Rend le code de sortie, garde la sortie dans $SORTIE.
  SORTIE="$(sh "$SCRIPT" "$@" --une-fois 2>&1)" && CODE=0 || CODE=$?
  export SORTIE CODE
}

compter() { find "$1" -maxdepth 1 -name "$2" 2>/dev/null | wc -l | tr -d ' '; }
marqueur() { [ -f "$DESTINATION/.derniere-reussite-$1" ] && echo oui || echo non; }

echo "Sauvegarde de la base"

decor base-ok
lancer base
verifier "un dump réussi sort en 0" "$CODE" "0"
verifier "  … écrit un fichier" "$(compter "$DESTINATION/base" '*.dump')" "1"
verifier "  … et une copie mensuelle" "$(compter "$DESTINATION/base/mensuel" '*.dump')" "1"
verifier "  … et pose le marqueur de réussite" "$(marqueur base)" "oui"

decor base-echec
CODE_PGDUMP=1 lancer base
verifier "un pg_dump en échec sort en erreur" "$CODE" "1"
verifier "  … n'écrit aucun dump" "$(compter "$DESTINATION/base" '*.dump')" "0"
verifier "  … ne laisse pas de .partiel" "$(compter "$DESTINATION/base" '*.partiel')" "0"
verifier "  … ET NE POSE PAS LE MARQUEUR" "$(marqueur base)" "non"

decor base-vide
CONTENU_DUMP="" lancer base
verifier "un dump vide est refusé" "$CODE" "1"
verifier "  … aucun fichier conservé" "$(compter "$DESTINATION/base" '*.dump')" "0"
verifier "  … aucun marqueur" "$(marqueur base)" "non"

echo "Chiffrement à clé publique des dumps"

decor cle-publique
openssl req -x509 -newkey rsa:2048 -days 1 -nodes -keyout "$BAC/privee.pem" \
    -out "$BAC/publique.pem" -subj "/CN=Test" >/dev/null 2>&1
SAUVEGARDE_CLE_PUBLIQUE="$BAC/publique.pem" CONTENU_DUMP="PGDMP-contenu-secret" lancer base
verifier "un dump chiffré sort en 0" "$CODE" "0"
verifier "  … porte le suffixe .enc" "$(compter "$DESTINATION/base" '*.dump.enc')" "1"
verifier "  … et aucun dump en clair" "$(compter "$DESTINATION/base" '*.dump')" "0"
chiffre="$(find "$DESTINATION/base" -maxdepth 1 -name '*.dump.enc' | head -1)"
verifier "  … dont le contenu n'est pas lisible" \
  "$(compte 'contenu-secret' "$chiffre")" "0"
dechiffre="$(openssl smime -decrypt -binary -inform DER -in "$chiffre" \
    -inkey "$BAC/privee.pem" 2>/dev/null)"
verifier "  … et se déchiffre avec la clé privée" "$dechiffre" "PGDMP-contenu-secret"

decor cle-publique-absente
SAUVEGARDE_CLE_PUBLIQUE="$BAC/inexistante.pem" lancer base
verifier "une clé publique introuvable arrête tout" "$CODE" "1"
verifier "  … sans marqueur" "$(marqueur base)" "non"

decor cle-publique-pgdump-ko
# Le cas que `set -o pipefail` attraperait ailleurs : pg_dump échoue **dans
# le tube**, openssl réussit. Sans le fichier témoin, un dump chiffré vide
# aurait été pris pour une sauvegarde.
SAUVEGARDE_CLE_PUBLIQUE="$BAC/publique.pem" CODE_PGDUMP=1 lancer base
verifier "un pg_dump raté dans le tube est vu" "$CODE" "1"
verifier "  … aucun .enc conservé" "$(compter "$DESTINATION/base" '*.dump.enc')" "0"
verifier "  … aucun marqueur" "$(marqueur base)" "non"

echo "Miroir des justificatifs"

decor pieces-ok
lancer pieces
verifier "un miroir réussi sort en 0" "$CODE" "0"
verifier "  … pose le marqueur" "$(marqueur pieces)" "oui"

decor pieces-echec
CODE_MC=1 lancer pieces
verifier "un mc en échec sort en erreur" "$CODE" "1"
verifier "  … sans marqueur" "$(marqueur pieces)" "non"

echo "Copie hors machine"

decor distant-sans-cle
export SAUVEGARDE_DISTANT_ENDPOINT="https://exemple.invalid"
export SAUVEGARDE_DISTANT_BUCKET="seau" SAUVEGARDE_DISTANT_CLE="cle"
export SAUVEGARDE_DISTANT_SECRET="secret"
mkdir -p "$DESTINATION/base" && printf 'PGDMP' > "$DESTINATION/base/x.dump"
lancer distant
verifier "sans clé de chiffrement, la copie est refusée" "$CODE" "1"
verifier "  … et rien n'a été envoyé" "$(compte '^copy' "$JOURNAL_RCLONE")" "0"
verifier "  … sans marqueur" "$(marqueur distant)" "non"

decor distant-en-clair-explicite
export SAUVEGARDE_DISTANT_ENDPOINT="https://exemple.invalid"
export SAUVEGARDE_DISTANT_BUCKET="seau" SAUVEGARDE_DISTANT_CLE="cle"
export SAUVEGARDE_DISTANT_SECRET="secret" SAUVEGARDE_DISTANT_EN_CLAIR=1
mkdir -p "$DESTINATION/base" && printf 'PGDMP' > "$DESTINATION/base/x.dump"
lancer distant
verifier "en clair, seulement si on le demande" "$CODE" "0"
verifier_au_moins_une_fois "  … l'avertissement est écrit" \
  "$(printf '%s' "$SORTIE" | compte 'EN CLAIR')"

decor distant-chiffre
export SAUVEGARDE_DISTANT_ENDPOINT="https://exemple.invalid"
export SAUVEGARDE_DISTANT_BUCKET="seau" SAUVEGARDE_DISTANT_CLE="cle"
export SAUVEGARDE_DISTANT_SECRET="secret" SAUVEGARDE_CHIFFREMENT_CLE="phrase-longue"
mkdir -p "$DESTINATION/base" && printf 'PGDMP' > "$DESTINATION/base/x.dump"
lancer distant
verifier "avec la clé, la copie part" "$CODE" "0"
verifier "  … vers le coffre chiffré, pas le bucket nu" \
  "$(compte 'coffre:' "$JOURNAL_RCLONE")" "$(compte 'copy\|cryptcheck\|check' "$JOURNAL_RCLONE")"
verifier "  … et pose le marqueur" "$(marqueur distant)" "oui"
verifier "  … sans rien supprimer là-bas (rotation par le bucket)" \
  "$(compte '^delete' "$JOURNAL_RCLONE")" "0"

decor distant-copie-interrompue
export SAUVEGARDE_DISTANT_ENDPOINT="https://exemple.invalid"
export SAUVEGARDE_DISTANT_BUCKET="seau" SAUVEGARDE_DISTANT_CLE="cle"
export SAUVEGARDE_DISTANT_SECRET="secret" SAUVEGARDE_CHIFFREMENT_CLE="phrase-longue"
mkdir -p "$DESTINATION/base" && printf 'PGDMP' > "$DESTINATION/base/x.dump"
CODE_RCLONE=1 lancer distant
verifier "une copie interrompue sort en erreur" "$CODE" "1"
verifier "  … ET NE POSE PAS LE MARQUEUR" "$(marqueur distant)" "non"

decor distant-verification-ko
export SAUVEGARDE_DISTANT_ENDPOINT="https://exemple.invalid"
export SAUVEGARDE_DISTANT_BUCKET="seau" SAUVEGARDE_DISTANT_CLE="cle"
export SAUVEGARDE_DISTANT_SECRET="secret" SAUVEGARDE_CHIFFREMENT_CLE="phrase-longue"
mkdir -p "$DESTINATION/base" && printf 'PGDMP' > "$DESTINATION/base/x.dump"
CODE_RCLONE_CHECK=1 lancer distant
verifier "une copie non vérifiée sort en erreur" "$CODE" "1"
verifier "  … sans marqueur : « copié » n'est pas « vérifié »" "$(marqueur distant)" "non"

decor distant-rotation-demandee
export SAUVEGARDE_DISTANT_ENDPOINT="https://exemple.invalid"
export SAUVEGARDE_DISTANT_BUCKET="seau" SAUVEGARDE_DISTANT_CLE="cle"
export SAUVEGARDE_DISTANT_SECRET="secret" SAUVEGARDE_CHIFFREMENT_CLE="phrase-longue"
export SAUVEGARDE_DISTANT_ROTATION=1
mkdir -p "$DESTINATION/base" && printf 'PGDMP' > "$DESTINATION/base/x.dump"
lancer distant
verifier "la rotation d'ici ne se fait que si on la demande" \
  "$(compte '^delete' "$JOURNAL_RCLONE")" "1"

echo
if [ "$echecs" -eq 0 ]; then
  echo "✔ $reussis contrôles passés."
  exit 0
fi
echo "✘ $echecs contrôle(s) en échec sur $((reussis + echecs))." >&2
exit 1
