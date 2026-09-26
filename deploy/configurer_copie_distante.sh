#!/bin/sh
# Met en service la copie hors machine des sauvegardes, en une commande,
# depuis le poste de l'exploitant (décision 95).
#
#   deploy/configurer_copie_distante.sh root@<hôte>
#
# Ce qu'il fait, dans l'ordre :
#   1. met le dépôt local à jour (`git pull --ff-only`) ;
#   2. envoie deploy/ sur le serveur et le rend à root — l'étape qu'un
#      `rsync -a` seul oublie, et sans laquelle la livraison suivante est
#      refusée (livraison v1.3.0 du 25 septembre 2026) ;
#   3. demande les réglages du bucket Cloudflare R2 — les secrets sans les
#      afficher — et les écrit dans le .env du serveur, après en avoir fait
#      une copie datée ;
#   4. recrée `sauvegarde-distante`, lance une première copie et
#      `verifier_sauvegardes`.
#
# Les secrets ne passent ni par la ligne de commande (visible dans `ps`) ni
# par l'historique du shell : ils sont lus au clavier, masqués, et transmis
# au serveur par l'entrée standard de SSH.
#
# Ce qu'il ne fait pas : créer le bucket, ses règles de cycle de vie, ses
# verrous et la clé d'API. Cela se fait dans le tableau de bord Cloudflare,
# avant (deploy/README.md, « Copie hors machine »).
set -eu

HOTE="${1:?usage : deploy/configurer_copie_distante.sh root@<hôte>}"
# Surchargeable pour le test (deploy/tests/test_configurer_copie_distante.sh).
REPERTOIRE="${JUSTI_REPERTOIRE:-/home/deploy/justi-innov}"

cd "$(dirname "$0")/.."

echo "→ Mise à jour du dépôt local…"
git pull --ff-only

echo "→ Envoi de deploy/ sur $HOTE, rendu à root…"
rsync -a --exclude .env --exclude .deployed deploy/ "$HOTE:$REPERTOIRE/"
# Le chemin est développé ici, côté poste : c'est voulu.
# shellcheck disable=SC2029
ssh "$HOTE" "chown -R root:root $REPERTOIRE && chmod 755 $REPERTOIRE/*.sh && chmod 600 $REPERTOIRE/.env && install -m 0755 $REPERTOIRE/justi-livrer /usr/local/bin/justi-livrer"
# shellcheck disable=SC2029
if ! ssh "$HOTE" "grep -q 'Cloudflare) export' $REPERTOIRE/sauvegarder.sh"; then
  echo "✘ le serveur n'a pas le sauvegarder.sh qui sait parler à R2 : la PR de la décision 95 est-elle fusionnée ?" >&2
  exit 1
fi

demander() {
  # demander <invite> <défaut> [masqué]
  printf '%s' "$1" >&2
  [ -n "$2" ] && printf ' [%s]' "$2" >&2
  printf ' : ' >&2
  if [ "${3:-}" = masque ]; then
    stty -echo 2>/dev/null || true
    IFS= read -r reponse || true
    stty echo 2>/dev/null || true
    printf '\n' >&2
  else
    IFS= read -r reponse || true
  fi
  printf '%s' "${reponse:-$2}"
}

echo ""
echo "Réglages du bucket Cloudflare R2 (tableau de bord › R2) :"
ENDPOINT="$(demander "Endpoint S3 (https://<id>.r2.cloudflarestorage.com ou …eu.r2…)" "")"
BUCKET="$(demander "Nom du bucket" "sauvegardes-justi-gh-prod")"
CLE="$(demander "Access Key ID" "")"
SECRET="$(demander "Secret Access Key (masquée)" "" masque)"
CHIFFREMENT="$(demander "Clé de chiffrement, celle du coffre (masquée)" "" masque)"

refuser() { echo "✘ $1 — rien n'a été écrit sur le serveur." >&2; exit 1; }
case "$ENDPOINT" in https://*.r2.cloudflarestorage.com) ;; *) refuser "endpoint inattendu : « $ENDPOINT »" ;; esac
[ -n "$BUCKET" ] && [ -n "$CLE" ] && [ -n "$SECRET" ] && [ -n "$CHIFFREMENT" ] \
  || refuser "une valeur est vide"
# Les valeurs voyagent entre apostrophes jusqu'au serveur : une apostrophe
# ou un retour à la ligne les casserait. Aucune clé R2 ni sortie
# d'`openssl rand -base64` n'en contient.
for valeur in "$ENDPOINT" "$BUCKET" "$CLE" "$SECRET" "$CHIFFREMENT"; do
  case "$valeur" in *"'"*|*"
"*) refuser "une valeur contient une apostrophe ou un retour à la ligne" ;; esac
done
[ "${#CHIFFREMENT}" -ge 32 ] || refuser "la clé de chiffrement fait moins de 32 caractères : tirez-la avec « openssl rand -base64 48 »"

echo ""
echo "→ Écriture du .env du serveur (copie de l'ancien à côté), puis première copie…"
# Le document est développé ici, côté poste : les valeurs saisies y entrent
# telles quelles (bornées plus haut), les « \$ » restent pour le serveur.
# shellcheck disable=SC2087
ssh "$HOTE" "sh -s" <<SUR_LE_SERVEUR
set -eu
cd $REPERTOIRE
cp -p .env ".env.avant-distant-\$(date -u +%Y%m%dT%H%M%SZ)"
poser() {
  # poser <clé> <valeur> : remplace la ligne, ou l'ajoute à la fin.
  if grep -q "^\$1=" .env; then
    VALEUR="\$2" awk -v cle="\$1" 'index(\$0, cle "=") == 1 { print cle "=" ENVIRON["VALEUR"]; next } { print }' .env > .env.nouveau
    cat .env.nouveau > .env && rm -f .env.nouveau
  else
    printf '%s=%s\n' "\$1" "\$2" >> .env
  fi
}
poser SAUVEGARDE_DISTANT_ENDPOINT '$ENDPOINT'
poser SAUVEGARDE_DISTANT_BUCKET '$BUCKET'
poser SAUVEGARDE_DISTANT_CLE '$CLE'
poser SAUVEGARDE_DISTANT_SECRET '$SECRET'
poser SAUVEGARDE_DISTANT_REGION 'auto'
poser SAUVEGARDE_DISTANT_FOURNISSEUR 'Cloudflare'
poser SAUVEGARDE_CHIFFREMENT_CLE '$CHIFFREMENT'
chown root:root .env && chmod 600 .env
echo "  .env :"
grep -E '^SAUVEGARDE_(DISTANT|CHIFFREMENT)' .env | sed -E 's/=(.+)\$/=<renseigné>/; s/^/    /'
C="docker compose -f docker-compose.prod.yml"
\$C up -d sauvegarde-distante
statut=0
\$C run --rm -T sauvegarde-distante --une-fois || statut=1
\$C exec -T scheduler python manage.py verifier_sauvegardes || true
exit \$statut
SUR_LE_SERVEUR

echo ""
echo "✔ Terminé. Chaque famille doit avoir son « ✔ copie distante » ci-dessus."
echo "  La clé de chiffrement n'existe plus que dans le .env du serveur et dans votre coffre : vérifiez qu'elle y est."
