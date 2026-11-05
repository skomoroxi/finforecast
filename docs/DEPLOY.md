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
   gh secret set DEPLOY_SSH_KEY --repo skomoroxi/finforecast < "%USERPROFILE%\.ssh\finforecast_gha"
   ```
   That is for Windows `cmd`, which does not understand `~`. In Git Bash use `< ~/.ssh/finforecast_gha`.
3. **API keys** for milestone 2: put them into `/opt/finforecast/.env` on the server (`TWELVEDATA_API_KEY`,
   `ALPHAVANTAGE_API_KEY`, `FRED_API_KEY`, `FINNHUB_API_KEY`), then `docker compose up -d` in that folder.
4. **Admin user** (Windows `cmd`):
   ```bash
   ssh -t -i "%USERPROFILE%\.ssh\finforecast_ed25519" root@91.210.170.44 "docker exec -it finforecast-web-1 python manage.py createsuperuser"
   ```
   The admin path is printed by the setup script (`ADMIN_URL` in `.env`).

## Operations

| Task | Command (on the server, in `/opt/finforecast`) |
|---|---|
| Status | `docker compose ps` |
| Logs | `docker compose logs -f --tail 100 web worker beat` |
| Health | `curl -s 127.0.0.1:8000/healthz` |
| Restart | `docker compose restart web worker beat` |
| Load missing price history | `docker exec finforecast-web-1 python manage.py backfill_prices` |
| Manual deploy | GitHub → Actions → Deploy → Run workflow |

## Daily data jobs (UTC)

| Time | Job |
|---|---|
| 00:15 daily | crypto |
| 00:30 Tue-Sat | FX, gold, silver |
| 00:50 Tue-Sat | shares and ETFs (after FX: German shares need that day's EUR/USD) |
| 03:15 Tue-Sat | oil, Brent, heating oil |
| 04:00 daily | ADR ratio for the 2 shares checked longest ago |
| every 3 min, US market hours | live quotes into Redis |

Results are in the admin under Fetch runs. A failed asset keeps its old data and the run carries on.

## Known constraints
- The server is short of memory. On 2026-11-04 and 2026-11-05 a burst of PHP requests (Apache allows 150 workers)
  used up RAM and swap and the kernel killed mysqld; systemd restarted it. The app's containers therefore carry a high
  `oom_score_adj`, so they go first. `mem_limit` caps RAM only: this kernel has no swap accounting (`swapaccount=1`
  plus a reboot would add it).
- EIA's API refuses this server's Russian IP range (HTTP 403, with or without a key), so heating oil comes from
  FRED's API, series DHOILNYH, which republishes the same EIA data. FRED's CSV endpoint is not reachable from here.
- Ubuntu 18.04 is past standard support; Docker is pinned at 24.0.2 (last release for 18.04). Plan an OS upgrade or a new VPS.
- 1.9 GB RAM shared with other sites, plus 2 GB swap. Upgrading to 4 GB RAM is the most useful improvement.
