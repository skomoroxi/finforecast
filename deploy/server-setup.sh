#!/usr/bin/env bash
# One-time setup of a plain Ubuntu VPS (Hostman, 2 vCPU / 4 GB) for FinForecast. Run as root:
#   ssh root@SERVER 'bash -s' < deploy/server-setup.sh
# Idempotent: safe to run again. Packages come from the Ubuntu archive only.
# The .env is not created here: copy the existing one (docs/DEPLOY.md, "Moving the site").
set -euo pipefail

DEPLOY_PUBKEY='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAZlw+QpL/eOeAqrAiPJWrFbzEoiTQ4BZwzlP8H/w3Up github-actions deploy skomoroxi/finforecast'
APP=/opt/finforecast
DOMAIN=price-predictions.net
HOSTMAN_MONITORING="92.53.116.12 92.53.116.111 92.53.116.119"   # Zabbix servers in the agent config

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq docker.io docker-compose-v2 caddy ufw unattended-upgrades >/dev/null
systemctl enable --now docker

# 1. Firewall: SSH and web only (+ the hosting provider's monitoring agent).
#    The app listens on 127.0.0.1:8000, so Docker's own iptables rules expose nothing.
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
for ip in $HOSTMAN_MONITORING; do ufw allow from "$ip" to any port 10050 proto tcp >/dev/null; done
ufw --force enable >/dev/null

# 2. "deploy" user for GitHub Actions: may run docker, owns the app folder, nothing else.
id deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/bash deploy
usermod -aG docker deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
echo "$DEPLOY_PUBKEY" > /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys && chmod 600 /home/deploy/.ssh/authorized_keys
install -d -m 750 -o deploy -g deploy "$APP"

# 3. Caddy: HTTPS with an automatic Let's Encrypt certificate, www -> bare domain, proxy to the app.
#    The certificate is issued once DNS points here; until then Caddy retries on its own.
cat > /etc/caddy/Caddyfile <<EOF
www.$DOMAIN {
	redir https://$DOMAIN{uri} permanent
}

$DOMAIN {
	encode gzip
	reverse_proxy 127.0.0.1:8000
	log {
		output file /var/log/caddy/access.log {
			roll_size 20MiB
			roll_keep 5
		}
	}
}
EOF
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
systemctl enable caddy >/dev/null
systemctl reload-or-restart caddy

echo "Server setup done."
