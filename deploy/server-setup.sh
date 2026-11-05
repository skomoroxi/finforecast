#!/usr/bin/env bash
# One-time server setup for FinForecast on the ISPmanager VPS. Run as root:
#   ssh root@91.210.170.44 'bash -s' < deploy/server-setup.sh
# Idempotent: safe to run again. Does not touch other sites, mail or ISPmanager settings.
set -euo pipefail

DEPLOY_PUBKEY='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAZlw+QpL/eOeAqrAiPJWrFbzEoiTQ4BZwzlP8H/w3Up github-actions deploy skomoroxi/finforecast'
APP=/opt/finforecast
DOCROOT=/var/www/clauforecast/data/www/forecast/public   # ISPmanager docroot of price-predictions.net

# 1. "deploy" user for GitHub Actions: may run docker, owns the app folder, nothing else.
id deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/bash deploy
usermod -aG docker deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
echo "$DEPLOY_PUBKEY" > /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys && chmod 600 /home/deploy/.ssh/authorized_keys
install -d -m 750 -o deploy -g deploy "$APP"

# 2. Production .env with random secrets, created once, never printed.
ENV="$APP/.env"
if [ ! -f "$ENV" ]; then
  PW=$(openssl rand -hex 24)
  SK=$(openssl rand -base64 64 | tr -d '\n/+=' | cut -c1-64)
  AP=$(openssl rand -hex 6)
  cat > "$ENV" <<EOF
DEBUG=false
DJANGO_SECRET_KEY=$SK
ALLOWED_HOSTS=price-predictions.net,www.price-predictions.net,127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=https://price-predictions.net,https://www.price-predictions.net
SITE_URL=https://price-predictions.net
INDEXING=false
ADMIN_URL=manage-$AP/
POSTGRES_DB=finforecast
POSTGRES_USER=finforecast
POSTGRES_PASSWORD=$PW
DATABASE_URL=postgres://finforecast:$PW@db:5432/finforecast
REDIS_URL=redis://redis:6379/0
TWELVEDATA_API_KEY=
ALPHAVANTAGE_API_KEY=
EIA_API_KEY=
FINNHUB_API_KEY=
EOF
  chown deploy:deploy "$ENV" && chmod 600 "$ENV"
fi

# 3. Apache (ISPmanager) forwards price-predictions.net to the app on 127.0.0.1:8000.
#    Done with .htaccess in the domain's docroot so ISPmanager regenerating the vhost cannot undo it.
a2enmod -q proxy proxy_http headers rewrite
apache2ctl configtest
systemctl reload apache2
install -d -o clauforecast -g clauforecast "$DOCROOT"
cat > "$DOCROOT/.htaccess" <<'EOF'
# FinForecast: everything goes to the Django app in Docker (deploy/server-setup.sh)
DirectoryIndex disabled
RewriteEngine On
RequestHeader set X-Forwarded-Proto "https" env=HTTPS
RewriteRule ^(.*)$ http://127.0.0.1:8000/$1 [P,L]
EOF
chown clauforecast:clauforecast "$DOCROOT/.htaccess"

echo "Server setup done."
echo "Admin path: $(grep ^ADMIN_URL "$ENV" | cut -d= -f2)"
