#!/bin/sh
# Tests de `justi-livrer`, la commande forcée de la clé de livraison —
# sans SSH, sans Docker, sans root.
#
#   deploy/tests/test_justi_livrer.sh
#
# Le script ne fait confiance qu'à deux choses sur le serveur : la
# propriété des fichiers (`stat -c %U`) et la marque ENVIRONNEMENT. Ici,
# `stat` est une doublure qui répond « root » (ou ce qu'on lui demande), et
# le deploy.sh du répertoire d'exploitation n'écrit que ce qu'il reçoit.
# On éprouve ce qui compte : **une livraison destinée à un environnement
# ne se déploie jamais sur l'autre**, ni sur un serveur qui ne dit pas ce
# qu'il est (décision 90).
#
# La CI l'exécute (`ci.yml`, travail « Exploitation ») ; en local, il ne
# touche qu'un répertoire temporaire, qu'il efface en sortant.
set -eu

ICI="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$ICI/../justi-livrer"
[ -f "$SCRIPT" ] || { echo "✘ justi-livrer introuvable à côté de tests/" >&2; exit 2; }

BAC="$(mktemp -d)"
trap 'rm -rf "$BAC"' EXIT
DOUBLURES="$BAC/bin"
REPERTOIRE="$BAC/justi-innov"
mkdir -p "$DOUBLURES" "$REPERTOIRE"
PATH="$DOUBLURES:$PATH"
export PATH

reussis=0
echecs=0

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
# `stat -c %U <fichier>` : PROPRIETAIRE (root par défaut). Le vrai `stat`
# rendrait le compte qui exécute le test, jamais root en CI.
cat > "$DOUBLURES/stat" <<'EOF'
#!/bin/sh
echo "${PROPRIETAIRE:-root}"
EOF
chmod +x "$DOUBLURES/stat"

# Le deploy.sh du serveur : il note ce qu'il a reçu, rien d'autre.
cat > "$REPERTOIRE/deploy.sh" <<'EOF'
#!/bin/sh
echo "$IMAGE_TAG $APP_DOMAIN" > "$(dirname "$0")/deploye"
EOF
chmod +x "$REPERTOIRE/deploy.sh"

COMMANDE_PROD="livrer sha-3a0ab3a8902b ghcr.io/org/depot-backend ghcr.io/org/depot-frontend exemple.org alamine2003 production"
COMMANDE_PREPROD="livrer sha-3a0ab3a8902b ghcr.io/org/depot-backend ghcr.io/org/depot-frontend preprod.exemple.org alamine2003 staging"

# lancer <commande> : exécute justi-livrer, pose CODE et DEPLOYE.
lancer() {
  rm -f "$REPERTOIRE/deploye"
  CODE=0
  SSH_ORIGINAL_COMMAND="$1" JUSTI_REPERTOIRE="$REPERTOIRE" sh "$SCRIPT" \
    > "$BAC/sortie" 2>&1 || CODE=$?
  if [ -f "$REPERTOIRE/deploye" ]; then DEPLOYE=oui; else DEPLOYE=non; fi
}

echo "— Serveur de production"
echo production > "$REPERTOIRE/ENVIRONNEMENT"

lancer "$COMMANDE_PROD"
verifier "une livraison de production s'y déploie" "$CODE/$DEPLOYE" "0/oui"
verifier "  … avec l'étiquette et le domaine demandés" "$(cat "$REPERTOIRE/deploye")" "sha-3a0ab3a8902b exemple.org"

lancer "$COMMANDE_PREPROD"
verifier "une livraison de préproduction y est refusée" "$CODE/$DEPLOYE" "2/non"
verifier "  … et le refus dit pourquoi" \
  "$(grep -c 'ce serveur est « production », la livraison vise « staging »' "$BAC/sortie")" "1"

lancer "livrer sha-3a0ab3a8902b ghcr.io/org/depot-backend ghcr.io/org/depot-frontend exemple.org alamine2003"
verifier "l'ancienne forme, sans environnement, est refusée" "$CODE/$DEPLOYE" "2/non"

lancer "livrer sha-3a0ab3a8902b ghcr.io/org/depot-backend ghcr.io/org/depot-frontend exemple.org alamine2003 recette"
verifier "un environnement inconnu est refusé" "$CODE/$DEPLOYE" "2/non"

echo "— Serveur de préproduction"
printf 'staging\n' > "$REPERTOIRE/ENVIRONNEMENT"

lancer "$COMMANDE_PREPROD"
verifier "une livraison de préproduction s'y déploie" "$CODE/$DEPLOYE" "0/oui"

lancer "$COMMANDE_PROD"
verifier "une livraison de production y est refusée" "$CODE/$DEPLOYE" "2/non"

echo "— Serveur qui ne dit pas ce qu'il est"
rm -f "$REPERTOIRE/ENVIRONNEMENT"

lancer "$COMMANDE_PROD"
verifier "sans marque, rien ne se déploie" "$CODE/$DEPLOYE" "2/non"
verifier "  … et le refus nomme le fichier à écrire" \
  "$(grep -c 'ENVIRONNEMENT absent' "$BAC/sortie")" "1"

echo production > "$REPERTOIRE/ENVIRONNEMENT"
PROPRIETAIRE=deploy lancer "$COMMANDE_PROD"
verifier "une marque qui n'appartient pas à root ne vaut rien" "$CODE/$DEPLOYE" "2/non"

echo
if [ "$echecs" -eq 0 ]; then
  echo "✔ $reussis contrôles passés."
  exit 0
fi
echo "✘ $echecs contrôle(s) en échec sur $((reussis + echecs))." >&2
exit 1
