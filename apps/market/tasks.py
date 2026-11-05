"""Scheduled data jobs (TECHNICAL-TASK §13). The schedule is CELERY_BEAT_SCHEDULE in settings."""

import logging

from celery import shared_task
from django.core.cache import cache
from django.db.models import F

from . import services
from .models import AdrConversion, Asset
from .sources import SourceError, finnhub

log = logging.getLogger(__name__)

GROUPS = {
    "crypto": ["crypto"],
    "fx_metal": ["fx", "metal"],
    "energy": ["energy"],
    "stocks": ["etf_index", "stock"],
}
RATIOS_PER_DAY = 2  # 14 shares a week; 2 of the 25 daily Alpha Vantage requests
LIVE_TTL = 1800


def _enabled():
    return Asset.objects.filter(enabled=True).select_related("asset_class", "proxy", "adr", "adr__adr_asset")


@shared_task
def update_group(group: str) -> None:
    services.run_assets(f"update:{group}", _enabled().filter(asset_class__code__in=GROUPS[group]))


@shared_task
def update_codes(codes: list[str], full: bool = False) -> None:
    services.run_assets("update:manual", _enabled().filter(code__in=codes), full=full)


@shared_task
def backfill(only_missing: bool = True) -> None:
    """Load full history. Safe to repeat: with only_missing it picks up whatever is still empty."""
    assets = _enabled().filter(bars__isnull=True).distinct() if only_missing else _enabled()
    services.run_assets("backfill", assets, full=True)


@shared_task
def recalc_ratios() -> None:
    conversions = AdrConversion.objects.filter(asset__enabled=True).order_by(
        F("ratio_updated_at").asc(nulls_first=True)
    )
    assets = _enabled().filter(adr__in=[c.pk for c in conversions[:RATIOS_PER_DAY]])
    services.run_assets("adr-ratio", assets, action=lambda asset: services.recalc_ratio(asset.adr))


@shared_task
def rebuild_adr(asset_code: str) -> None:
    assets = _enabled().filter(code=asset_code)
    services.run_assets("adr-rebuild", assets, action=lambda asset: services.rebuild_adr(asset.adr))


@shared_task
def refresh_live_quotes() -> None:
    source = finnhub()
    for code, symbol in Asset.objects.filter(enabled=True).exclude(live_symbol="").values_list("code", "live_symbol"):
        try:
            cache.set(f"live:{code}", source.quote(symbol), timeout=LIVE_TTL)
        except SourceError as exc:
            log.warning("live quote %s: %s", code, exc)
