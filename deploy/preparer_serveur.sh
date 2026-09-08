#!/usr/bin/env bash
# Prépare une machine Ubuntu 24.04 neuve pour recevoir la pile de production
# (« Préparer un serveur », README.md de ce dossier) : Docker Engine et son
# plugin Compose, l'utilisateur `deploy` — SANS le groupe docker, qui vaut
# root — dont la clé SSH ne peut exécuter que la commande forcée de
# livraison (justi-livrer, par un sudo restreint à elle seule), le
# répertoire d'exploitation propriété de root, le pare-feu (22, 80, 443)
# et les mises à jour de sécurité automatiques. Idempotent.
#
# Depuis votre poste : d'abord les fichiers d'exploitation, en root, puis ce
# script, la clé publique de déploiement en argument :
#
#   rsync -a --exclude .env deploy/ root@<hôte>:/home/deploy/justi-innov/
#   ssh root@<hôte> "bash -s -- '$(cat ~/.ssh/justi-innov-deploy.pub)'" \
#       < deploy/preparer_serveur.sh
#
# Les humains entrent en root, avec la clé que l'hébergeur y a posée : le
# compte `deploy` ne sert qu'à la livraison continue, et ne peut rien
# d'autre (README.md, « Réduire les pouvoirs de la livraison »).
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8

CLE_DEPLOIEMENT="${1:?clé publique de déploiement attendue en argument}"
case "$CLE_DEPLOIEMENT" in
  ssh-ed25519\ *|ssh-rsa\ *|ecdsa-sha2-*) ;;
  *) echo "argument inattendu : ce n'est pas une clé publique SSH" >&2; exit 1 ;;
esac

echo "== Paquets"
apt-get update -q
apt-get install -yq ca-certificates curl ufw unattended-upgrades

echo "== Docker"
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi
systemctl enable --now docker

echo "== Utilisateur deploy : hors du groupe docker, une seule commande"
REPERTOIRE=/home/deploy/justi-innov
if [ ! -f "$REPERTOIRE/justi-livrer" ]; then
  echo "✘ $REPERTOIRE/justi-livrer absent : copiez d'abord deploy/ (rsync, voir l'en-tête)." >&2
  exit 1
fi
id deploy >/dev/null 2>&1 || adduser --disabled-password --gecos "" deploy
gpasswd -d deploy docker >/dev/null 2>&1 || true
install -o root -g root -m 0755 "$REPERTOIRE/justi-livrer" /usr/local/bin/justi-livrer
cat > /etc/sudoers.d/justi-livrer <<'EOF'
# La clé de livraison ne peut exécuter que ceci, en root, sans mot de passe.
Defaults!/usr/local/bin/justi-livrer env_keep += "SSH_ORIGINAL_COMMAND"
deploy ALL=(root) NOPASSWD: /usr/local/bin/justi-livrer
EOF
chmod 0440 /etc/sudoers.d/justi-livrer
visudo -cf /etc/sudoers.d/justi-livrer >/dev/null
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
printf 'command="sudo -n /usr/local/bin/justi-livrer",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty %s\n' \
  "$CLE_DEPLOIEMENT" > /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
# Le répertoire d'exploitation appartient à root : la clé de livraison ne
# peut pas remplacer ce qu'elle exécute, ni lire le .env.
chown -R root:root "$REPERTOIRE"
find "$REPERTOIRE" -type d -exec chmod 755 {} +
find "$REPERTOIRE" -type f -exec chmod 644 {} +
chmod 755 "$REPERTOIRE"/*.sh
if [ -f "$REPERTOIRE/.env" ]; then chmod 600 "$REPERTOIRE/.env"; fi

echo "== Pare-feu"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow OpenSSH >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

echo "== Mises à jour de sécurité automatiques"
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "== SSH : clés seulement"
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh

echo
echo "Prêt : $(docker --version) · compose $(docker compose version --short) · $(nproc) cœurs · $(free -h | awk 'NR==2{print $2}') RAM · $(df -h / | awk 'NR==2{print $4}') libres"
