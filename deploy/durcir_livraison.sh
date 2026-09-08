#!/usr/bin/env bash
# Réduit les pouvoirs de la livraison sur un serveur déjà en service
# (audit du 8 septembre 2026, §3.4). Idempotent. En root :
#
#   ssh root@<hôte> "bash -s -- '$(cat ~/.ssh/justi-innov-deploy.pub)'" \
#       < deploy/durcir_livraison.sh
#
# Avant : le compte `deploy` était membre du groupe docker — ce qui vaut
# root —, la livraison recopiait tout deploy/ depuis le dépôt puis
# exécutait le deploy.sh qu'elle venait d'écrire : quiconque pousse sur
# `main` exécutait du code en root sur le serveur, sans approbation.
#
# Après : `deploy` n'est plus dans le groupe docker ; sa clé ne peut
# exécuter qu'une commande forcée (justi-livrer, propriété de root, par un
# sudo restreint à elle seule), qui valide chaque argument et lance le
# deploy.sh du répertoire d'exploitation — lui aussi propriété de root, que
# la clé ne peut pas remplacer. Le .env n'est lisible que par root. La CI
# ne change plus jamais ce qui tourne en root : les fichiers d'exploitation
# se mettent à jour en root (README.md, « Réduire les pouvoirs de la
# livraison »). Les clés des humains ne sont plus sur `deploy` : ils
# entrent en root, comme l'hébergeur les y a mis.
#
# Le script attend le fichier justi-livrer à côté de lui (stdin est le
# script : on le lit depuis le dépôt local, voir README). Retour arrière :
# README.md, même section.
set -euo pipefail

CLE_DEPLOIEMENT="${1:?clé publique de déploiement attendue en argument}"
case "$CLE_DEPLOIEMENT" in
  ssh-ed25519\ *|ssh-rsa\ *|ecdsa-sha2-*) ;;
  *) echo "argument inattendu : ce n'est pas une clé publique SSH" >&2; exit 1 ;;
esac
REPERTOIRE=/home/deploy/justi-innov

echo "== Commande forcée"
if [ ! -f "$REPERTOIRE/justi-livrer" ]; then
  echo "✘ $REPERTOIRE/justi-livrer absent : copiez d'abord deploy/justi-livrer sur le serveur." >&2
  exit 1
fi
install -o root -g root -m 0755 "$REPERTOIRE/justi-livrer" /usr/local/bin/justi-livrer

echo "== Utilisateur deploy : hors du groupe docker, sudo restreint"
id deploy >/dev/null 2>&1 || adduser --disabled-password --gecos "" deploy
gpasswd -d deploy docker >/dev/null 2>&1 || true
cat > /etc/sudoers.d/justi-livrer <<'EOF'
# La clé de livraison ne peut exécuter que ceci, en root, sans mot de passe.
Defaults!/usr/local/bin/justi-livrer env_keep += "SSH_ORIGINAL_COMMAND"
deploy ALL=(root) NOPASSWD: /usr/local/bin/justi-livrer
EOF
chmod 0440 /etc/sudoers.d/justi-livrer
visudo -cf /etc/sudoers.d/justi-livrer >/dev/null

echo "== Clé de livraison : commande forcée, rien d'autre"
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
printf 'command="sudo -n /usr/local/bin/justi-livrer",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty %s\n' \
  "$CLE_DEPLOIEMENT" > /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys

echo "== Répertoire d'exploitation : propriété de root"
install -d -m 755 -o root -g root "$REPERTOIRE"
chown -R root:root "$REPERTOIRE"
find "$REPERTOIRE" -type d -exec chmod 755 {} +
find "$REPERTOIRE" -type f -exec chmod 644 {} +
chmod 755 "$REPERTOIRE"/*.sh
if [ -f "$REPERTOIRE/.env" ]; then chmod 600 "$REPERTOIRE/.env"; fi
rm -f "$REPERTOIRE/.deploy-env"

echo
echo "Prêt. Vérification, depuis votre poste, avec la clé de livraison :"
echo "  ssh -i ~/.ssh/justi-innov-deploy deploy@<hôte> id           → doit répondre « livraison refusée »"
echo "  ssh -i ~/.ssh/justi-innov-deploy deploy@<hôte> 'livrer x'   → doit répondre « forme attendue »"
echo "et sur le serveur : id deploy → sans « docker » ; sudo -l -U deploy → justi-livrer seul."
