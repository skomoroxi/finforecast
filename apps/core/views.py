from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache

from apps.core.tasks import HEARTBEAT_KEY


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
