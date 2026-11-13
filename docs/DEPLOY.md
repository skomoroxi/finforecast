# Deployment

```
push to main ─► CI (lint, tests on TimescaleDB + Redis, image build)
                 └─ green ─► Deploy: build image → scp to VPS → docker load → migrate → compose up → /healthz
Browser ─► Caddy (HTTPS, Let's Encrypt, price-predictions.net) ─► 127.0.0.1:8000 (Docker: web)
```

The VPS (Hostman, Frankfurt, 212.192.2.86, Ubuntu 26.04, 2 vCPU / 4 GB / 80 GB NVMe) runs only this project.
The app runs entirely in Docker (`/opt/finforecast`): PostgreSQL 16 + TimescaleDB, Redis, Django (gunicorn), Celery
worker and beat, with memory limits. Only port 8000 on 127.0.0.1 is published; Caddy (an Ubuntu package, not Docker)
terminates HTTPS on 80/443. The firewall (ufw) allows 22, 80, 443 and Hostman's monitoring agent on 10050.
The domain's DNS and mail stay at Timeweb (A records for `price-predictions.net` and `www` point here).

## One-time setup

1. **Server** (as root, reviewed script): `ssh root@212.192.2.86 'bash -s' < deploy/server-setup.sh`
   - installs Docker, Docker Compose, Caddy and ufw from the Ubuntu archive; sets up the firewall
   - creates the `deploy` user (docker group, SSH key of GitHub Actions only) and `/opt/finforecast`
   - writes `/etc/caddy/Caddyfile` (HTTPS, `www` redirects to the bare domain, proxy to the app)
2. **`.env`**: copy the existing `/opt/finforecast/.env` (owner `deploy`, mode 600). It holds every secret: database
   password, Django key, admin path, API keys. Never commit it or paste it anywhere.
3. **GitHub**: secret `DEPLOY_SSH_KEY` (private key of GitHub Actions) and variable `DEPLOY_HOST` (server IP);
   the server's SSH host key goes into `deploy/known_hosts`.
   ```bash
   gh secret set DEPLOY_SSH_KEY --repo skomoroxi/finforecast < ~/.ssh/finforecast_gha
   gh variable set DEPLOY_HOST --repo skomoroxi/finforecast --body 212.192.2.86
   ```
4. **Admin user**: `docker exec -it finforecast-web-1 python manage.py createsuperuser`.
   The admin path is `ADMIN_URL` in `.env`.

## Moving the site to another server

1. Run steps 1–2 above on the new server; copy the app image from the old one
   (`docker save finforecast:TAG | gzip` → `gunzip | docker load`) plus `docker-compose.yml` and `deploy/remote-deploy.sh`.
2. On the old server stop the jobs (`docker compose stop worker beat`) so data stops changing and API quotas are not
   used twice, then dump: `docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > db.dump`.
3. On the new server: `docker compose up -d db redis`, then restore into the empty database:
   `SELECT timescaledb_pre_restore();` → `pg_restore --no-owner -d finforecast` → `SELECT timescaledb_post_restore();`.
4. `docker compose up -d web worker beat`; test with `curl -H "Host: price-predictions.net" 127.0.0.1:8000/healthz`.
5. Point the DNS A records at the new IP. Caddy gets the certificate by itself once DNS resolves to it.
6. Update `DEPLOY_HOST` and `deploy/known_hosts` (step 3 above). Keep the old server until the new one has run a night.

## Operations

| Task | Command (on the server, in `/opt/finforecast`) |
|---|---|
| Status | `docker compose ps` |
| Logs | `docker compose logs -f --tail 100 web worker beat` |
| Health | `curl -s 127.0.0.1:8000/healthz` |
| Restart | `docker compose restart web worker beat` |
| Web server | `systemctl status caddy`; config `/etc/caddy/Caddyfile`; log `/var/log/caddy/access.log` |
| Load missing price history | `docker exec finforecast-web-1 python manage.py backfill_prices` |
| Manual deploy | GitHub → Actions → Deploy → Run workflow |

## Admin login

Staff sign in with a username and password at the secret admin path (`ADMIN_URL` in `.env`). There is no second
factor (removed at the owner's request on 2026-11-07), so use a long, unique password. To set a new one:

```bash
docker exec -it finforecast-web-1 python manage.py changepassword <username>
```

## Daily data jobs (UTC)

| Time | Job |
|---|---|
| 00:15 daily | crypto |
| 00:30 Tue-Sat | FX, gold, silver |
| 00:50 Tue-Sat | shares and ETFs (after FX: German shares need that day's EUR/USD) |
| 01:30 daily | forecasts that are due |
| 03:15 Tue-Sat | oil, Brent, heating oil |
| 03:45 daily | energy forecasts |
| 04:00 daily | ADR ratio for the 2 shares checked longest ago |
| 04:30 daily | forecast accuracy |
| every 3 min, US market hours | live quotes into Redis |

Results are in the admin under Fetch runs. A failed asset keeps its old data and the run carries on.

## History
- Until 2026-11-13 the site ran on a shared ISPmanager VPS in Russia (91.210.170.44, Ubuntu 18.04, 2 GB, behind
  Apache). That is why heating oil comes from FRED's API (series DHOILNYH, which republishes EIA data): EIA refused
  Russian IPs. From the new server EIA can be used again.
