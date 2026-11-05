# FinForecast (price-predictions.net)

Multilingual price-forecast site: Django 5.2 LTS, PostgreSQL 16 + TimescaleDB, Redis, Celery, Docker Compose.
Specification: [docs/TECHNICAL-TASK.md](docs/TECHNICAL-TASK.md). Deployment: [docs/DEPLOY.md](docs/DEPLOY.md).

## Status
- [x] **M1: skeleton.** Django project, Docker Compose stack, CI (lint, tests on TimescaleDB + Redis, image build), deploy workflow, server setup script.
- [x] **M2: data.** 87 instruments, provider adapters with rate limits, daily jobs, German shares in euros from ADRs, fetch log.
- [ ] M3: models and accuracy · M4: content engine · M5: admin · M6: front end · M7: en + de · M8: SEO · M9: legal · M10: launch

## Local development
```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # macOS/Linux: .venv/bin/pip
# needs PostgreSQL with TimescaleDB and Redis, e.g.:
docker run -d --name ff-db -e POSTGRES_USER=finforecast -e POSTGRES_PASSWORD=finforecast -p 5432:5432 timescale/timescaledb:2.31.0-pg16
docker run -d --name ff-redis -p 6379:6379 redis:7.4.9-alpine
.venv/Scripts/python manage.py migrate && .venv/Scripts/python manage.py runserver
.venv/Scripts/pytest
```
