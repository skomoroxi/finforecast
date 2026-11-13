# FinForecast (large project)

- **Spec:** `docs/TECHNICAL-TASK.md` (Russian). Milestones in §15; current milestone in README "Status".
- **Deploy and server:** `docs/DEPLOY.md`. Dedicated Hostman VPS (212.192.2.86) set up by `deploy/server-setup.sh`;
  Caddy for HTTPS, everything else in Docker. DNS and mail for the domain stay at Timeweb.
- **Predecessor:** the small static site `skomoroxi/forecast` holds the forecasting pipeline, TA rules and design system
  to port (TECHNICAL-TASK §4, §5.1).

## Rules
- Production runs on the Hostman VPS in Frankfurt since 2026-11-13. Keep everything portable. Never proxy around a
  geo-block.
- Secrets only in `/opt/finforecast/.env` on the server and GitHub Secrets; never in the repo or logs.
- 4 GB RAM, dedicated: keep Celery concurrency 1 and the compose memory limits.
- Every page is `noindex` until `INDEXING=true` at launch.
- Default template vs admin override rule for every page field: TECHNICAL-TASK §7. Template syntax: `apps/content/templating.py`.
- `apps/content/defaults.py` only seeds the database; the admin owns templates after that.

## Commands
- `.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .`
- `.venv/Scripts/pytest` (needs PostgreSQL+TimescaleDB and Redis; see README)
- `python manage.py makemigrations --check --dry-run`
