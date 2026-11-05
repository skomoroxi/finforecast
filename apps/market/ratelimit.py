"""Per-provider pacing and daily budgets, shared through Redis (TECHNICAL-TASK §3.3)."""

import time
from dataclasses import dataclass

from django.core.cache import cache
from django.utils import timezone


class BudgetExceeded(RuntimeError):
    """The provider's daily allowance is used up; try again tomorrow."""


@dataclass(frozen=True)
class Limit:
    interval: float  # seconds between requests
    per_day: int | None = None


LIMITS = {
    "twelvedata": Limit(interval=8.0, per_day=800),  # free plan: 8 a minute, 800 a day
    "alphavantage": Limit(interval=1.5, per_day=25),
    "binance": Limit(interval=0.3),
    "kraken": Limit(interval=1.0),
    "fred": Limit(interval=0.6),  # 120 a minute
    "finnhub": Limit(interval=1.05),  # 60 a minute
}


def acquire(provider: str) -> None:
    """Block until the next request to `provider` is allowed. Raises BudgetExceeded when none are left today."""
    limit = LIMITS[provider]
    if limit.per_day is not None:
        key = f"rl:{provider}:{timezone.now():%Y-%m-%d}"
        cache.add(key, 0, timeout=2 * 86400)
        if cache.incr(key) > limit.per_day:
            raise BudgetExceeded(f"{provider} daily budget of {limit.per_day} requests is used up")
    key = f"rl:{provider}:last"
    wait = (cache.get(key) or 0) + limit.interval - time.time()
    if wait > 0:
        time.sleep(wait)
    cache.set(key, time.time(), timeout=600)
