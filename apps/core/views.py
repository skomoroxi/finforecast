from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from apps.core.tasks import HEARTBEAT_KEY


def home(request):
    # Placeholder until the asset pages exist (milestone 6).
    return render(request, "core/home.html")


@never_cache
def healthz(request):
    """Liveness for monitoring: database (with TimescaleDB), Redis and the last Celery heartbeat."""
    status = {"db": False, "timescaledb": None, "redis": False, "celery_heartbeat": None}
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")
            row = cur.fetchone()
        status["db"] = True
        status["timescaledb"] = row[0] if row else None
    except Exception:  # noqa: BLE001 - health check reports, never raises
        pass
    try:
        cache.set("core:ping", 1, timeout=10)
        status["redis"] = cache.get("core:ping") == 1
        status["celery_heartbeat"] = cache.get(HEARTBEAT_KEY)
    except Exception:  # noqa: BLE001
        pass
    ok = status["db"] and status["redis"]
    return JsonResponse(status, status=200 if ok else 503)


def robots(request):
    """Closed until launch (INDEXING=True), like the small site."""
    if settings.INDEXING:
        body = f"User-agent: *\nAllow: /\nDisallow: /{settings.ADMIN_URL}\n\nSitemap: {settings.SITE_URL}/sitemap.xml\n"
    else:
        body = "# Pre-launch: nothing is indexed yet.\nUser-agent: *\nDisallow: /\n"
    return HttpResponse(body, content_type="text/plain; charset=utf-8")
