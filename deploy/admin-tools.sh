#!/usr/bin/env bash
# Admin tools on the Hostman VPS: Cockpit (files, services, logs, terminal) and Adminer (MariaDB + PostgreSQL).
# Both listen on 127.0.0.1 only; reach them through an SSH tunnel:
#   ssh -N -L 9090:127.0.0.1:9090 -L 8082:127.0.0.1:8082 root@212.192.2.86
# then open https://localhost:9090 (Cockpit, self-signed certificate: accept the browser warning once) and
# http://localhost:8082 (Adminer). Idempotent.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq --no-install-recommends cockpit-ws cockpit-system cockpit-bridge cockpit-files adminer php-pgsql >/dev/null

# Cockpit: local only, over its own HTTPS (self-signed). Plain HTTP (AllowUnencrypted) signs in but the session's
# websocket never attaches, so it times out after 15 s (seen with Cockpit 360 on Ubuntu 26.04).
install -d /etc/systemd/system/cockpit.socket.d
cat > /etc/systemd/system/cockpit.socket.d/listen.conf <<'CONF'
[Socket]
ListenStream=
ListenStream=127.0.0.1:9090
CONF
cat > /etc/cockpit/cockpit.conf <<'CONF'
[WebService]
Origins = https://localhost:9090 https://127.0.0.1:9090

[Session]
IdleTimeout = 30
CONF
systemctl daemon-reload
systemctl enable cockpit.socket >/dev/null 2>&1
systemctl restart cockpit.socket

# Adminer: its own PHP-FPM pool and a Caddy site bound to 127.0.0.1:8082.
PHPV=$(php -r 'echo PHP_MAJOR_VERSION.".".PHP_MINOR_VERSION;')
ADMINER_DIR=$(dirname "$(dpkg -L adminer | grep -E '/adminer\.php$' | head -1)")
id adminer >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin adminer
cat > /etc/php/$PHPV/fpm/pool.d/adminer.conf <<CONF
[adminer]
user = adminer
group = adminer
listen = /run/php/adminer.sock
listen.owner = caddy
listen.group = caddy
pm = ondemand
pm.max_children = 2
pm.process_idle_timeout = 30s
php_admin_value[memory_limit] = 256M
php_admin_value[upload_max_filesize] = 64M
php_admin_value[post_max_size] = 64M
php_admin_value[max_execution_time] = 300
php_admin_flag[display_errors] = off
CONF
systemctl reload php$PHPV-fpm

cat > /etc/caddy/sites/admin-tools.caddy <<CONF
# Adminer for MariaDB (127.0.0.1:3306) and PostgreSQL (127.0.0.1:5432). Local only: use the SSH tunnel.
http://127.0.0.1:8082, http://localhost:8082 {
	bind 127.0.0.1
	root * $ADMINER_DIR
	rewrite / /adminer.php
	php_fastcgi unix//run/php/adminer.sock
	file_server
}
CONF
caddy validate --config /etc/caddy/Caddyfile >/dev/null
systemctl reload caddy
echo "cockpit: $(systemctl is-active cockpit.socket)  adminer dir: $ADMINER_DIR"
