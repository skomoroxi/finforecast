#!/usr/bin/env bash
# Runs on the VPS as the "deploy" user (called by .github/workflows/deploy.yml).
set -euo pipefail
cd /opt/finforecast

: "${IMAGE_TAG:?IMAGE_TAG required}"
test -f .env || { echo ".env missing in /opt/finforecast (see docs/DEPLOY.md)"; exit 1; }

gunzip -c image.tar.gz | docker load
rm -f image.tar.gz
export IMAGE_TAG

# Remember the running version, so plain "docker compose ..." works here without IMAGE_TAG set.
if grep -q "^IMAGE_TAG=" .env; then sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=$IMAGE_TAG/" .env; else echo "IMAGE_TAG=$IMAGE_TAG" >> .env; fi

docker compose up -d db redis
docker compose run --rm web sh -c "python manage.py migrate --noinput && python manage.py seed_assets && python manage.py seed_templates"
docker compose up -d --remove-orphans web worker beat

# Keep the last 3 app images, drop the rest (the disk is shared with other sites).
docker images finforecast --format '{{.Tag}} {{.ID}}' | grep -v '^latest ' | tail -n +4 | awk '{print $2}' | xargs -r docker rmi -f >/dev/null 2>&1 || true
docker image prune -f >/dev/null

docker compose ps   # compose 2.18 on this server: no Go-template --format
