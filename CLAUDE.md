# FinForecast (large project)

- **Spec:** `docs/TECHNICAL-TASK.md` (Russian). Milestones in §15; current milestone in README "Status".
- **Deploy and server:** `docs/DEPLOY.md`. The VPS hosts other live sites and mail via ISPmanager: never change Apache,
  MySQL, mail or ISPmanager settings beyond what `deploy/server-setup.sh` does, and never touch other docroots.
- **Predecessor:** the small static site `skomoroxi/forecast` holds the forecasting pipeline, TA rules and design system
  to port (TECHNICAL-TASK §4, §5.1).

## Rules
- The current VPS is a development sandbox. Production moves to a non-Russian server when the site is built, so keep
  everything portable. Never proxy around a geo-block. Claude API features run for real only after the move.
- Secrets only in `/opt/finforecast/.env` on the server and GitHub Secrets; never in the repo or logs.
- Memory is tight (1.9 GB shared): keep Celery concurrency 1 and the compose memory limits.
- Every page is `noindex` until `INDEXING=true` at launch.
- Default template vs admin override rule for every page field: TECHNICAL-TASK §7.

## Commands
- `.venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .`
- `.venv/Scripts/pytest` (needs PostgreSQL+TimescaleDB and Redis; see README)
- `python manage.py makemigrations --check --dry-run`
