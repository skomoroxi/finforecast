"""Fetch, check and store prices; estimate German shares in euros; keep the run log."""

import bisect
import logging
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from django.db.models import Max
from django.utils import timezone

from .models import AdrConversion, Asset, Basis, Calendar, FetchResult, FetchRun, PriceBar, Source
from .sources import Bar, SourceError, get_source

log = logging.getLogger(__name__)

FULL_HISTORY = 5000
RECENT_BARS = 10
RATIO_DAYS = 100
RATIO_MIN_DAYS = 20
RATIO_MAX_JUMP = Decimal("0.10")
EURUSD = "EURUSD"
# Dependencies first: EUR/USD before the shares priced from it.
CLASS_ORDER = ["fx", "metal", "energy", "crypto", "etf_index", "stock"]


class PriceJump(SourceError):
    """A new close moved more than the class allows; a person should look before it is stored."""


class RatioPaused(SourceError):
    """An ADR ratio jumped; the share stops updating until the admin decides."""


def clean_bars(bars: list[Bar], calendar: str, today: date) -> list[Bar]:
    """Drop the unfinished current day, weekends on weekday calendars, and non-positive prices."""
    return [b for b in bars if b.date < today and b.close > 0 and (calendar == Calendar.CRYPTO or b.date.weekday() < 5)]


def check_jumps(previous_close: Decimal | None, bars: list[Bar], max_change: float) -> None:
    limit = Decimal(str(max_change))
    previous = previous_close
    for bar in bars:
        if previous and abs(bar.close / previous - 1) > limit:
            raise PriceJump(f"{bar.date}: close {bar.close} is more than {limit:.0%} from {previous}")
        previous = bar.close


def average(bar: Bar) -> Decimal:
    if bar.high is not None and bar.low is not None:
        return (bar.high + bar.low + bar.close) / 3
    return bar.close


def save_bars(asset: Asset, bars: list[Bar], source: str) -> int:
    rows = [
        PriceBar(
            asset=asset,
            date=b.date,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            avg=average(b),
            volume=b.volume,
            source=source,
            basis=b.basis,
        )
        for b in bars
    ]
    PriceBar.objects.bulk_create(
        rows,
        batch_size=1000,
        update_conflicts=True,
        unique_fields=["asset", "date"],
        update_fields=["open", "high", "low", "close", "avg", "volume", "source", "basis"],
    )
    return len(rows)


def apply_proxy(bars: list[Bar], proxy: Asset) -> list[Bar]:
    """Estimate a close-only asset's day range from its tracking instrument, scaled to the real close."""
    wanted = [b.date for b in bars if b.basis == Basis.CLOSE]
    by_date = {p.date: p for p in PriceBar.objects.filter(asset=proxy, date__in=wanted)}
    out = []
    for bar in bars:
        p = by_date.get(bar.date)
        if bar.basis != Basis.CLOSE or p is None or p.high is None:
            out.append(bar)
            continue
        k = bar.close / p.close
        open_ = p.open * k
        out.append(
            Bar(
                date=bar.date,
                close=bar.close,
                open=open_,
                high=max(p.high * k, open_, bar.close),
                low=min(p.low * k, open_, bar.close),
                basis=Basis.PROXY,
            )
        )
    return out


def fetch(asset: Asset, count: int) -> tuple[list[Bar], str]:
    """Bars from the asset's source, or from its fallback if that fails."""
    try:
        return get_source(asset.source).daily_bars(asset.symbol, count), asset.source
    except SourceError as primary:
        if not asset.fallback_source:
            raise
        log.warning("%s: %s; trying %s", asset.code, primary, asset.fallback_source)
        return get_source(asset.fallback_source).daily_bars(asset.fallback_symbol, count), asset.fallback_source


def update_asset(asset: Asset, full: bool = False) -> tuple[int, date | None, str]:
    """Bring one asset up to date. Returns (bars written, last date, source)."""
    if asset.source == Source.ADR:
        return update_adr(asset.adr, full=full)

    today = timezone.now().date()
    calendar = asset.asset_class.calendar
    last = PriceBar.objects.filter(asset=asset).aggregate(last=Max("date"))["last"]
    full = full or last is None  # a new asset, or one whose key arrived later, loads its history by itself
    count = FULL_HISTORY if full else max(RECENT_BARS, (today - last).days + 5)

    bars, used = fetch(asset, count)
    bars = clean_bars(bars, calendar, today)
    if not bars:
        raise SourceError("no finished bars in the response")

    if not full:
        known = PriceBar.objects.filter(asset=asset, date__lt=bars[0].date).order_by("-date").first()
        check_jumps(known.close if known else None, bars, asset.asset_class.max_daily_change)
    if asset.proxy_id:
        bars = apply_proxy(bars, asset.proxy)

    written = save_bars(asset, bars, used)
    if full and asset.history_source:
        older = get_source(asset.history_source).daily_bars(asset.history_symbol, FULL_HISTORY)
        older = [b for b in clean_bars(older, calendar, today) if b.date < bars[0].date]
        written += save_bars(asset, older, asset.history_source)
    return written, bars[-1].date, used


class FxRates:
    """EUR/USD closes, carrying the last known rate over days without one."""

    def __init__(self):
        rows = PriceBar.objects.filter(asset__code=EURUSD).order_by("date").values_list("date", "close")
        self._dates = [d for d, _ in rows]
        self._rates = [r for _, r in rows]

    def on(self, day: date) -> Decimal | None:
        i = bisect.bisect_right(self._dates, day)
        return self._rates[i - 1] if i else None


def recalc_ratio(conv: AdrConversion) -> tuple[int, date | None, str]:
    """Median of XETRA close x EUR/USD / ADR close over the last 100 days, then rebuild the euro series."""
    today = timezone.now().date()
    source = get_source(Source.ALPHAVANTAGE)
    xetra = clean_bars(source.daily_bars(conv.xetra_symbol, RATIO_DAYS), Calendar.NYSE, today)
    save_bars(conv.asset, xetra, Source.ALPHAVANTAGE)  # real closes are worth keeping whatever the ratio says

    adr = dict(
        PriceBar.objects.filter(asset=conv.adr_asset, date__in=[b.date for b in xetra]).values_list("date", "close")
    )
    fx = FxRates()
    ratios = [b.close * fx.on(b.date) / adr[b.date] for b in xetra if b.date in adr and fx.on(b.date)]
    conv.ratio_updated_at = timezone.now()
    if len(ratios) < RATIO_MIN_DAYS:
        conv.save(update_fields=["ratio_updated_at"])
        raise SourceError(f"only {len(ratios)} days overlap between {conv.xetra_symbol} and its ADR")

    new = median(ratios).quantize(Decimal("0.00000001"))
    if conv.ratio_auto and abs(new / conv.ratio_auto - 1) > RATIO_MAX_JUMP:
        conv.ratio_candidate = new
        conv.status = AdrConversion.Status.PAUSED
        conv.save(update_fields=["ratio_updated_at", "ratio_candidate", "status"])
        raise RatioPaused(f"ADR ratio moved from {conv.ratio_auto} to {new}; waiting for a decision in the admin")

    conv.ratio_auto = new
    conv.ratio_candidate = None
    conv.status = AdrConversion.Status.OK
    conv.save(update_fields=["ratio_updated_at", "ratio_auto", "ratio_candidate", "status"])
    return rebuild_adr(conv)


def rebuild_adr(conv: AdrConversion, since: date | None = None) -> tuple[int, date | None, str]:
    """Euro prices from ADR x ratio / EUR/USD, leaving real XETRA closes alone."""
    if conv.ratio is None:
        raise SourceError("no ADR ratio yet")
    fx = FxRates()
    real = set(PriceBar.objects.filter(asset=conv.asset, source=Source.ALPHAVANTAGE).values_list("date", flat=True))
    adr_bars = PriceBar.objects.filter(asset=conv.adr_asset).order_by("date")
    if since:
        adr_bars = adr_bars.filter(date__gte=since)

    bars = []
    for bar in adr_bars:
        rate = fx.on(bar.date)
        if bar.date in real or not rate:
            continue
        k = conv.ratio / rate
        bars.append(
            Bar(
                date=bar.date,
                close=bar.close * k,
                open=bar.open * k if bar.open is not None else None,
                high=bar.high * k if bar.high is not None else None,
                low=bar.low * k if bar.low is not None else None,
                basis=Basis.ESTIMATE,
            )
        )
    written = save_bars(conv.asset, bars, Source.ADR)
    return written, bars[-1].date if bars else None, Source.ADR


def update_adr(conv: AdrConversion, full: bool = False) -> tuple[int, date | None, str]:
    if conv.status == AdrConversion.Status.PAUSED and conv.ratio_manual is None:
        raise RatioPaused("ADR ratio is paused; decide in the admin")
    if conv.ratio is None:
        return recalc_ratio(conv)
    since = None if full else timezone.now().date() - timedelta(days=15)
    return rebuild_adr(conv, since)


def run_assets(task: str, assets, action=update_asset, **kwargs) -> FetchRun:
    """Run `action` per asset. One asset failing never stops the others; it keeps yesterday's data."""
    assets = sorted(
        assets,
        key=lambda a: (CLASS_ORDER.index(a.asset_class.code), a.series_of_id is None, a.order),
    )
    run = FetchRun.objects.create(task=task)
    for asset in assets:
        try:
            bars, last_date, source = action(asset, **kwargs)
        except Exception as exc:  # noqa: BLE001 - the whole point is to carry on with the next asset
            run.error_count += 1
            message = f"{type(exc).__name__}: {exc}"[:300]
            log.error("%s %s: %s", task, asset.code, message)
            FetchResult.objects.create(run=run, asset=asset, ok=False, message=message)
        else:
            run.ok_count += 1
            FetchResult.objects.create(run=run, asset=asset, ok=True, source=source, bars=bars, last_date=last_date)
    run.finished_at = timezone.now()
    run.save(update_fields=["finished_at", "ok_count", "error_count"])
    log.info("%s: %d ok, %d failed", task, run.ok_count, run.error_count)
    return run
