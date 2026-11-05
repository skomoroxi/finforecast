"""Which accuracy figures a page shows. No heavy imports: the web process uses this."""

from .models import ForecastAccuracy

MIN_LIVE_SAMPLES = 30


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
