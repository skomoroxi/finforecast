"""Compare every matured stored forecast with the real price (TECHNICAL-TASK §11)."""

from datetime import date, timedelta

import pandas as pd
from django.db import connection
from django.utils import timezone

from apps.market.models import Asset, PriceBar

from .engine.backtest import HORIZONS
from .models import ForecastAccuracy

WINDOWS = (30, 90, 365)
MIN_LIVE_SAMPLES = 30

DAILY_SQL = """
    SELECT d.method, d.target, d.value, d.p10, d.p90, d.base, d.step, b.close AS actual
    FROM (
        SELECT p.method, p.target, p.value, p.p10, p.p90, r.last_close AS base,
               row_number() OVER (PARTITION BY p.run_id, p.method ORDER BY p.target) AS step
        FROM forecasts_forecastpoint p
        JOIN forecasts_forecastrun r ON r.id = p.run_id
        WHERE p.asset_id = %s AND p.horizon = 'daily' AND p.run_date >= %s
    ) d
    JOIN market_pricebar b ON b.asset_id = %s AND b.date = d.target
    WHERE d.step = ANY(%s)
"""

MONTHLY_SQL = """
    SELECT p.method, p.target, p.value, p.p10, p.p90, r.last_close AS base
    FROM forecasts_forecastpoint p
    JOIN forecasts_forecastrun r ON r.id = p.run_id
    WHERE p.asset_id = %s AND p.horizon = 'monthly' AND p.run_date >= %s
      AND p.target = (date_trunc('month', p.run_date) + INTERVAL '1 month')::date
"""


def metrics(rows: pd.DataFrame) -> dict:
    """`rows` has columns value, actual, base, p10, p90. All percentages, higher `bias_pct` means too high."""
    f, a, base = rows["value"], rows["actual"], rows["base"]
    banded = rows[rows["p10"].notna() & rows["p90"].notna()]
    in_range = None
    if len(banded):
        in_range = float(((banded["p10"] <= banded["actual"]) & (banded["actual"] <= banded["p90"])).mean() * 100)
    return {
        "mape": float(((f / a - 1).abs()).mean() * 100),
        "mae": float((f - a).abs().mean()),
        "direction_pct": float((((f - base) > 0) == ((a - base) > 0)).mean() * 100),
        "in_range_pct": in_range,
        "bias_pct": float((f / a - 1).mean() * 100),
        "samples": len(rows),
    }


def matured_daily(asset: Asset, since: date) -> pd.DataFrame:
    horizons = HORIZONS[asset.asset_class.calendar]
    with connection.cursor() as cursor:
        cursor.execute(DAILY_SQL, [asset.pk, since, asset.pk, list(horizons.values())])
        columns = [c.name for c in cursor.description]
        frame = pd.DataFrame(cursor.fetchall(), columns=columns)
    labels = {steps: label for label, steps in horizons.items()}
    return frame.assign(horizon=frame["step"].map(labels))


def matured_monthly(asset: Asset, since: date, today: date) -> pd.DataFrame:
    """Month averages for finished months: a forecast of next month, against what next month averaged."""
    with connection.cursor() as cursor:
        cursor.execute(MONTHLY_SQL, [asset.pk, since])
        columns = [c.name for c in cursor.description]
        frame = pd.DataFrame(cursor.fetchall(), columns=columns)
    if frame.empty:
        return frame
    bars = PriceBar.objects.filter(asset=asset, date__gte=frame["target"].min()).values_list("date", "close")
    closes = pd.Series({d: float(c) for d, c in bars})
    closes.index = pd.DatetimeIndex(closes.index)
    averages = closes.groupby(closes.index.to_period("M")).mean()
    this_month = pd.Timestamp(today).to_period("M")

    def actual(target):
        period = pd.Timestamp(target).to_period("M")
        return averages.get(period) if period < this_month else None

    frame = frame.assign(actual=frame["target"].map(actual), horizon="month").dropna(subset=["actual"])
    return frame


def rows_for(frame: pd.DataFrame, today: date) -> list[dict]:
    rows = []
    if frame.empty:
        return rows
    frame = frame.astype({"value": float, "base": float, "actual": float, "p10": float, "p90": float})
    for window in WINDOWS:
        recent = frame[frame["target"] >= today - timedelta(days=window)]
        for (method, horizon), group in recent.groupby(["method", "horizon"]):
            rows.append({"method": method, "horizon": horizon, "window_days": window} | metrics(group))
    return rows


def update_asset(asset: Asset) -> tuple[int, date, str]:
    today = timezone.now().date()
    since = today - timedelta(days=max(WINDOWS) + 45)
    frame = pd.concat([matured_daily(asset, since), matured_monthly(asset, since, today)], ignore_index=True)
    rows = rows_for(frame, today)
    ForecastAccuracy.objects.filter(asset=asset, basis=ForecastAccuracy.Basis.LIVE).delete()
    ForecastAccuracy.objects.bulk_create(
        ForecastAccuracy(asset=asset, basis=ForecastAccuracy.Basis.LIVE, computed_on=today, **row) for row in rows
    )
    return len(rows), today, "accuracy"


def for_display(asset: Asset) -> list[ForecastAccuracy]:
    """Live accuracy once a horizon has 30 matured forecasts, the walk-forward backtest until then."""
    rows = ForecastAccuracy.objects.filter(asset=asset)
    live = [r for r in rows if r.basis == ForecastAccuracy.Basis.LIVE]
    enough = {r.horizon for r in live if r.samples >= MIN_LIVE_SAMPLES}
    return [
        r
        for r in rows
        if (r.basis == ForecastAccuracy.Basis.LIVE and r.horizon in enough)
        or (r.basis == ForecastAccuracy.Basis.BACKTEST and r.horizon not in enough)
    ]
