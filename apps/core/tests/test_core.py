import pytest

from apps.core.tasks import HEARTBEAT_KEY, heartbeat


@pytest.mark.django_db
def test_home_is_noindex_before_launch(client, settings):
    settings.INDEXING = False
    r = client.get("/")
    assert r.status_code == 200
    assert b'content="noindex, nofollow"' in r.content


@pytest.mark.django_db
def test_healthz_reports_db_timescale_and_redis(client):
    heartbeat()
    data = client.get("/healthz").json()
    assert data["db"] is True
    assert data["timescaledb"]  # extension enabled by migration 0001
    assert data["redis"] is True
    assert data["celery_heartbeat"]


def test_robots_closed_until_indexing(client, settings):
    settings.INDEXING = False
    assert "Disallow: /" in client.get("/robots.txt").content.decode()
    settings.INDEXING = True
    body = client.get("/robots.txt").content.decode()
    assert "Allow: /" in body and "Sitemap:" not in body


def test_heartbeat_writes_cache(settings):
    from django.core.cache import cache

    ts = heartbeat()
    assert cache.get(HEARTBEAT_KEY) == ts


@pytest.mark.django_db
def test_admin_on_configured_path(client, settings):
    r = client.get(f"/{settings.ADMIN_URL}login/")
    assert r.status_code == 200
