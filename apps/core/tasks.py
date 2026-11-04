from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

HEARTBEAT_KEY = "core:heartbeat"


@shared_task
def heartbeat() -> str:
    """Proves the worker and beat are alive; /healthz reports the timestamp."""
    now = timezone.now().isoformat()
    cache.set(HEARTBEAT_KEY, now, timeout=None)
    return now
