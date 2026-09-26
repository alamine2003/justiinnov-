#!/bin/sh
# Tests de `configurer_copie_distante.sh` — sans serveur, sans Docker, sans
# réseau.
#
#   deploy/tests/test_configurer_copie_distante.sh
#
# `ssh` est une doublure qui exécute la commande ici même, dans un faux
# répertoire d'exploitation ; `git`, `rsync`, `chown`, `install` et `docker`
# ne font que noter qu'on les a appelés. On éprouve ce qui compte : le .env
# reçoit exactement les valeurs saisies, sans rien casser d'autre ; les
# secrets ne s'affichent pas ; une saisie invalide ou un serveur pas à jour
# n'écrivent rien.
set -eu

ICI="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$ICI/../configurer_copie_distante.sh"
[ -f "$SCRIPT" ] || { echo "✘ configurer_copie_distante.sh introuvable à côté de tests/" >&2; exit 2; }

BAC="$(mktemp -d)"
trap 'rm -rf "$BAC"' EXIT
DOUBLURES="$BAC/bin"
REPERTOIRE="$BAC/justi-innov"
mkdir -p "$DOUBLURES"
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
for outil in git rsync chown install; do
  printf '#!/bin/sh\necho "%s $*" >> "$BAC_JOURNAL"\n' "$outil" > "$DOUBLURES/$outil"
done
cat > "$DOUBLURES/docker" <<'EOF'
#!/bin/sh
echo "docker $*" >> "$BAC_JOURNAL"
case " $* " in *" run "*) exit "${CODE_COPIE:-0}" ;; esac
exit 0
EOF
# ssh <hôte> <commande> : la commande s'exécute ici, entrée standard comprise.
cat > "$DOUBLURES/ssh" <<'EOF'
#!/bin/sh
shift
exec sh -c "$*"
EOF
chmod +x "$DOUBLURES"/*

ENV_INITIAL='APP_DOMAIN=exemple.invalid
SAUVEGARDE_DISTANT_ENDPOINT=
SAUVEGARDE_DISTANT_BUCKET=
SAUVEGARDE_DISTANT_CLE=
SAUVEGARDE_DISTANT_SECRET=
SAUVEGARDE_DISTANT_REGION=
REGLAGE_VOISIN=valeur/avec+signes=fin'

CLE_CHIFFREMENT="Zm9vYmFyYmF6cXV4K3Rlc3QvY2xlZGVjaGlmZnJlbWVudA=="

# decor [avec-r2|sans-r2] : un faux serveur, son .env et son sauvegarder.sh.
decor() {
  rm -rf "$REPERTOIRE"
  mkdir -p "$REPERTOIRE"
  printf '%s\n' "$ENV_INITIAL" > "$REPERTOIRE/.env"
  if [ "$1" = avec-r2 ]; then
    echo '    Cloudflare) export RCLONE_CONFIG_DISTANT_NO_CHECK_BUCKET=true ;;' > "$REPERTOIRE/sauvegarder.sh"
  else
    echo '# ancien script' > "$REPERTOIRE/sauvegarder.sh"
  fi
  : > "$BAC/journal"
}

# lancer <saisie> : exécute le script, pose CODE et SORTIE.
lancer() {
  CODE=0
  printf '%s\n' "$1" | BAC_JOURNAL="$BAC/journal" JUSTI_REPERTOIRE="$REPERTOIRE" \
    sh "$SCRIPT" root@exemple.invalid > "$BAC/sortie" 2>&1 || CODE=$?
  SORTIE="$(cat "$BAC/sortie")"
}

valeur() { grep -E "^$1=" "$REPERTOIRE/.env" | tail -1 | cut -d= -f2-; }

CLE_ACCES="0123456789abcdef0123456789abcdef"
SECRET_ACCES="fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"

SAISIE_VALIDE="https://compte.eu.r2.cloudflarestorage.com

$CLE_ACCES
$SECRET_ACCES
$CLE_CHIFFREMENT"

echo "— Saisie valide"
decor avec-r2
lancer "$SAISIE_VALIDE"
verifier "le script réussit" "$CODE" "0"
verifier "  … endpoint écrit" "$(valeur SAUVEGARDE_DISTANT_ENDPOINT)" "https://compte.eu.r2.cloudflarestorage.com"
verifier "  … bucket par défaut" "$(valeur SAUVEGARDE_DISTANT_BUCKET)" "sauvegardes-justi-gh-prod"
verifier "  … clé d'accès" "$(valeur SAUVEGARDE_DISTANT_CLE)" "$CLE_ACCES"
verifier "  … secret intact" "$(valeur SAUVEGARDE_DISTANT_SECRET)" "$SECRET_ACCES"
verifier "  … région auto" "$(valeur SAUVEGARDE_DISTANT_REGION)" "auto"
verifier "  … fournisseur Cloudflare, ajouté" "$(valeur SAUVEGARDE_DISTANT_FOURNISSEUR)" "Cloudflare"
verifier "  … clé de chiffrement, ajoutée" "$(valeur SAUVEGARDE_CHIFFREMENT_CLE)" "$CLE_CHIFFREMENT"
verifier "  … les autres lignes n'ont pas bougé" \
  "$(valeur APP_DOMAIN) $(valeur REGLAGE_VOISIN)" "exemple.invalid valeur/avec+signes=fin"
verifier "  … chaque clé une seule fois" \
  "$(grep -c '^SAUVEGARDE_' "$REPERTOIRE/.env")" "7"
verifier "  … l'ancien .env est gardé à côté" \
  "$(ls "$REPERTOIRE"/.env.avant-distant-* 2>/dev/null | wc -l | tr -d ' ')" "1"
verifier "  … aucun secret affiché" \
  "$(printf '%s' "$SORTIE" | grep -c -e "$SECRET_ACCES" -e "$CLE_CHIFFREMENT" || true)" "0"
verifier "  … deploy/ envoyé puis rendu à root" \
  "$(grep -c -e "^rsync" -e "^chown -R root:root" "$BAC/journal")" "2"
verifier "  … service recréé, copie lancée, vérification lancée" \
  "$(grep -c -e 'up -d sauvegarde-distante' -e 'run --rm -T sauvegarde-distante --une-fois' -e 'verifier_sauvegardes' "$BAC/journal")" "3"

echo "— Copie en échec"
decor avec-r2
CODE_COPIE=1 lancer "$SAISIE_VALIDE"
verifier "une copie ratée fait échouer le script" "$CODE" "1"
verifier "  … la vérification a quand même tourné" \
  "$(grep -c 'verifier_sauvegardes' "$BAC/journal")" "1"

echo "— Saisies refusées : rien n'est écrit"
decor avec-r2
lancer "https://s3.eu-central-003.backblazeb2.com

$CLE_ACCES
$SECRET_ACCES
$CLE_CHIFFREMENT"
verifier "un endpoint qui n'est pas R2 est refusé" "$CODE" "1"
verifier "  … .env intact" "$(cat "$REPERTOIRE/.env")" "$ENV_INITIAL"

decor avec-r2
lancer "https://compte.r2.cloudflarestorage.com

$CLE_ACCES
$SECRET_ACCES
courte"
verifier "une clé de chiffrement trop courte est refusée" "$CODE" "1"
verifier "  … .env intact" "$(cat "$REPERTOIRE/.env")" "$ENV_INITIAL"

decor avec-r2
lancer "https://compte.r2.cloudflarestorage.com

$CLE_ACCES

$CLE_CHIFFREMENT"
verifier "un secret vide est refusé" "$CODE" "1"

decor avec-r2
lancer "https://compte.r2.cloudflarestorage.com

cle'id
$SECRET_ACCES
$CLE_CHIFFREMENT"
verifier "une apostrophe est refusée" "$CODE" "1"
verifier "  … .env intact" "$(cat "$REPERTOIRE/.env")" "$ENV_INITIAL"

decor avec-r2
lancer "https://compte.r2.cloudflarestorage.com

sauvegardes-justi-gh-prod$CLE_ACCES
$SECRET_ACCES
$CLE_CHIFFREMENT"
verifier "le nom du bucket collé devant la clé est refusé" "$CODE" "1"
verifier "  … .env intact" "$(cat "$REPERTOIRE/.env")" "$ENV_INITIAL"

decor avec-r2
lancer "https://compte.r2.cloudflarestorage.com

$SECRET_ACCES
$CLE_ACCES
$CLE_CHIFFREMENT"
verifier "le secret saisi à la place de la clé est refusé" "$CODE" "1"
verifier "  … .env intact" "$(cat "$REPERTOIRE/.env")" "$ENV_INITIAL"
verifier "  … le secret n'est pas répété à l'écran" \
  "$(printf '%s' "$SORTIE" | grep -c -e "$SECRET_ACCES" || true)" "0"

echo "— Serveur pas à jour"
decor sans-r2
lancer "$SAISIE_VALIDE"
verifier "un sauvegarder.sh qui ignore R2 arrête tout" "$CODE" "1"
verifier "  … avant toute question sur les secrets" "$(cat "$REPERTOIRE/.env")" "$ENV_INITIAL"

echo
if [ "$echecs" -eq 0 ]; then
  echo "✔ $reussis contrôles passés."
  exit 0
fi
echo "✘ $echecs contrôle(s) en échec sur $((reussis + echecs))." >&2
exit 1
