"""Which accuracy figures a page shows. No heavy imports: the web process uses this."""

from django.db import connection

from .models import ForecastAccuracy

MIN_LIVE_SAMPLES = 30
RECENT_ROWS = 10
MATURED_SQL = """
    SELECT d.target, d.value, b.close
    FROM (
        SELECT p.target, p.value, p.run_date,
               row_number() OVER (PARTITION BY p.run_id ORDER BY p.target) AS step
        FROM forecasts_forecastpoint p
        WHERE p.asset_id = %s AND p.horizon = 'daily' AND p.method = 'consensus'
    ) d
    JOIN market_pricebar b ON b.asset_id = %s AND b.date = d.target
    WHERE d.step = 1
    ORDER BY d.target DESC
    LIMIT %s
"""


def for_display(asset) -> list[ForecastAccuracy]:
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


def latest_accuracy(asset, method: str = "consensus") -> dict[str, ForecastAccuracy]:
    """Horizon to the row a sentence should quote; live uses the widest window."""
    rows = [r for r in for_display(asset) if r.method == method]
    rows.sort(key=lambda r: r.window_days)
    return {r.horizon: r for r in rows}


def recent_matured(asset) -> list[dict]:
    """The newest next-day forecasts whose real close is known."""
    with connection.cursor() as cursor:
        cursor.execute(MATURED_SQL, [asset.pk, asset.pk, RECENT_ROWS])
        return [{"target": t, "forecast": v, "actual": float(c)} for t, v, c in cursor.fetchall()]
