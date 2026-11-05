#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
trap 'echo "Ghost bootstrap failed at line $LINENO. Inspect cloud-init-output.log and systemctl status ghost cloudflared." >&2' ERR

chmod 700 /opt/ghost /etc/cloudflared
/usr/sbin/sshd -t
systemctl disable --now ssh.socket
systemctl daemon-reload
systemctl enable ssh.service
systemctl restart ssh.service

export DEBIAN_FRONTEND=noninteractive
apt-get update -o Acquire::Retries=3
apt-get install -y -o Acquire::Retries=3 ca-certificates curl python3 iptables docker.io docker-compose-v2

curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 \
  --retry 3 --connect-timeout 15 --max-time 180 \
  https://github.com/cloudflare/cloudflared/releases/download/2026.10.7/cloudflared-linux-amd64 \
  --output /opt/ghost/cloudflared.download
printf '%s\n' '1f99fb518b83dec2ba8d870a7cc991d82a77e6196295a3d2754ba17ab9f91872  /opt/ghost/cloudflared.download' | sha256sum --check --status
install -m 0755 /opt/ghost/cloudflared.download /usr/local/bin/cloudflared
rm /opt/ghost/cloudflared.download
systemctl enable --now cloudflared.service

python3 /opt/ghost/configure.py

systemctl enable --now docker.service
cd /opt/ghost
docker compose config --quiet
systemctl enable ghost.service
systemctl restart ghost.service
curl --fail --silent --show-error --retry 12 --retry-delay 5 --retry-connrefused --max-time 10 \
  http://127.0.0.1:2000/ready >/dev/null
systemctl is-active --quiet ssh.service cloudflared.service ghost.service
echo 'Ghost bootstrap completed.'
