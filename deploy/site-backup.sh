#!/usr/bin/env bash
# Full backup of price-predictions.net and online-invoice-generator.com into ONE archive:
#   /var/backups/sites/site-backup-YYYY-MM-DD_HHMM.tar   (mode 600: it contains passwords from .env and wp-config.php)
# Contents: finforecast.dump (PostgreSQL/TimescaleDB, pg_dump custom format), invoice-db.sql.gz (MariaDB),
# invoice-files.tar.gz (/var/www/invoice), server-config.tar.gz (/opt/finforecast incl. .env, Caddy, PHP pools,
# MariaDB tuning, admin tools), RESTORE.txt. Keeps the newest $KEEP archives. Install: /usr/local/sbin/site-backup.
set -euo pipefail
KEEP=${KEEP:-7}
OUT=/var/backups/sites
STAMP=$(date +%Y-%m-%d_%H%M)
WORK=$(mktemp -d "$OUT/.work-XXXX" 2>/dev/null || { install -d -m 700 "$OUT"; mktemp -d "$OUT/.work-XXXX"; })
trap 'rm -rf "$WORK"' EXIT
umask 077

cd /opt/finforecast
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$WORK/finforecast.dump" 2> "$WORK/pg_dump.log" || {
  cat "$WORK/pg_dump.log" >&2; exit 1; }
mysqldump --single-transaction --quick --routines --triggers --events --databases invoice-generate | gzip > "$WORK/invoice-db.sql.gz"
tar -czf "$WORK/invoice-files.tar.gz" -C /var/www invoice
tar -czf "$WORK/server-config.tar.gz" --ignore-failed-read -C / opt/finforecast etc/caddy \
  $(cd / && ls -d etc/php/*/fpm/pool.d) etc/mysql/mariadb.conf.d/90-small.cnf \
  etc/cockpit/cockpit.conf etc/systemd/system/cockpit.socket.d 2>/dev/null

cat > "$WORK/RESTORE.txt" <<'TXT'
Restore notes (backup made by /usr/local/sbin/site-backup)

price-predictions.net (Docker, TimescaleDB). On a server set up with deploy/server-setup.sh:
  1. Put back /opt/finforecast (from server-config.tar.gz), start only the db service:  docker compose up -d db
  2. docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT timescaledb_pre_restore();"'
  3. docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' < finforecast.dump
  4. docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT timescaledb_post_restore();"'
  5. docker compose up -d   (the app code comes from GitHub, skomoroxi/finforecast)

online-invoice-generator.com (WordPress, PHP-FPM, MariaDB). On a server set up with wp-setup.sh:
  1. tar -xzf invoice-files.tar.gz -C /var/www && chown -R invoice:invoice /var/www/invoice
  2. gunzip -c invoice-db.sql.gz | mysql     (creates the invoice-generate database; the DB user and password
     are in /var/www/invoice/public/wp-config.php and must exist in MariaDB)
  3. Caddy and PHP pool configs are in server-config.tar.gz (etc/caddy, etc/php/*/fpm/pool.d).
TXT

tar -cf "$OUT/site-backup-$STAMP.tar" -C "$WORK" finforecast.dump invoice-db.sql.gz invoice-files.tar.gz server-config.tar.gz RESTORE.txt
chmod 600 "$OUT/site-backup-$STAMP.tar"
ls -1t "$OUT"/site-backup-*.tar | tail -n +$((KEEP + 1)) | xargs -r rm -f
echo "$OUT/site-backup-$STAMP.tar $(du -h "$OUT/site-backup-$STAMP.tar" | cut -f1)"
