# Deployment

```
push to main ─► CI (lint, tests on TimescaleDB + Redis, image build)
                 └─ green ─► Deploy: build image → scp to VPS → docker load → migrate → compose up → /healthz
Browser ─► (Cloudflare, later) ─► Apache (ISPmanager, price-predictions.net) ─► 127.0.0.1:8000 (Docker: web)
```

The VPS (91.210.170.44, Ubuntu 18.04, ISPmanager) also hosts other sites and mail. The app runs entirely in Docker
(`/opt/finforecast`): PostgreSQL 16 + TimescaleDB, Redis, Django (gunicorn), Celery worker and beat, with memory limits.
Only port 8000 on 127.0.0.1 is published.

## One-time setup

1. **Server** (as root, reviewed script): `ssh root@91.210.170.44 'bash -s' < deploy/server-setup.sh`
   - creates the `deploy` user (docker group, SSH key of GitHub Actions only) and `/opt/finforecast`
   - writes `/opt/finforecast/.env` with random secrets (database password, Django key, admin path)
   - enables Apache proxy modules and puts `.htaccess` into the price-predictions.net docroot to forward to the app
2. **GitHub secret** (from the machine that holds the key):
   ```bash
   gh secret set DEPLOY_SSH_KEY --repo skomoroxi/finforecast < ~/.ssh/finforecast_gha
   ```
3. **API keys** for milestone 2: put them into `/opt/finforecast/.env` on the server (`TWELVEDATA_API_KEY`,
   `ALPHAVANTAGE_API_KEY`, `EIA_API_KEY`, `FINNHUB_API_KEY`), then `docker compose up -d` in that folder.
4. **Admin user**: `ssh root@91.210.170.44 "cd /opt/finforecast && docker compose run --rm web python manage.py createsuperuser"`
   The admin path is printed by the setup script (`ADMIN_URL` in `.env`).

## Operations

| Task | Command (on the server, in `/opt/finforecast`) |
|---|---|
| Status | `docker compose ps` |
| Logs | `docker compose logs -f --tail 100 web worker beat` |
| Health | `curl -s 127.0.0.1:8000/healthz` |
| Restart | `docker compose restart web worker beat` |
| Manual deploy | GitHub → Actions → Deploy → Run workflow |

## Known constraints
- Ubuntu 18.04 is past standard support; Docker is pinned at 24.0.2 (last release for 18.04). Plan an OS upgrade or a new VPS.
- 1.9 GB RAM shared with other sites, plus 2 GB swap. Upgrading to 4 GB RAM is the most useful improvement.
