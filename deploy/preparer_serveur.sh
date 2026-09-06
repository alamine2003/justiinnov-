#!/usr/bin/env bash
# Prépare une machine Ubuntu 24.04 neuve pour recevoir la pile de production
# (« Préparer un serveur », README.md de ce dossier) : Docker Engine et son
# plugin Compose, l'utilisateur `deploy` membre du groupe docker, sa clé SSH
# de déploiement, le pare-feu (22, 80, 443) et les mises à jour de sécurité
# automatiques. Idempotent : relançable sans dégât.
#
# Depuis votre poste, en root sur le serveur, la clé publique de déploiement
# en argument :
#
#   ssh root@<hôte> "bash -s -- '$(cat ~/.ssh/justi-innov-deploy.pub)'" \
#       < deploy/preparer_serveur.sh
#
# Les clés déjà autorisées pour root (celle de votre poste, posée par
# l'hébergeur) sont reprises pour `deploy`, afin que vous puissiez y ouvrir
# une session pour la première mise en service.
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

echo "== Utilisateur deploy"
id deploy >/dev/null 2>&1 || adduser --disabled-password --gecos "" deploy
usermod -aG docker deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
install -d -m 750 -o deploy -g deploy /home/deploy/justi-innov
touch /home/deploy/.ssh/authorized_keys
{ [ -f /root/.ssh/authorized_keys ] && cat /root/.ssh/authorized_keys; echo "$CLE_DEPLOIEMENT"; } \
  | sort -u > /home/deploy/.ssh/authorized_keys.tmp
mv /home/deploy/.ssh/authorized_keys.tmp /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh

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
