"""Run every method for one asset and turn the paths into the points we store (TECHNICAL-TASK §4, §6.3)."""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from . import arima, montecarlo, reversion
from .common import MethodForecast, bars_per_year, daily_drift_cap, failed, future_dates, sanity_check

MODEL_VERSION = "1.0"
METHODS = ("arima", "reversion", "montecarlo")
LONG_TERM_METHODS = ("reversion", "montecarlo")  # ARIMA adds nothing beyond 2030 (flat or pure drift)
MONTHLY_UNTIL = 2030
LAST_YEAR = 2035
DAILY_CALENDAR_DAYS = 30


@dataclass(frozen=True)
class Point:
    method: str
    horizon: str
    target: date
    value: float
    p10: float | None
    p90: float | None


def windows(calendar: str) -> dict:
    y = bars_per_year(calendar)
    return {
        "arima_bars": 5 * y,  # ARIMA: last 5 years
        "reversion_bars": 20 * y,  # trend + reversion: up to 20 years
        "mc_drift_bars": 10 * y,  # Monte Carlo drift: 10 years
        "mc_vol_bars": 3 * y,  # Monte Carlo volatility: 3 years
    }


def sig(x: float) -> float:
    """Round to 7 significant figures: 4 decimals would turn a $0.0000047 coin into zero."""
    return float(f"{float(x):.7g}")


def run_methods(close: pd.Series, dates, calendar: str, max_annual: float, seed: int, model=None) -> dict:
    w = windows(calendar)
    cap = daily_drift_cap(max_annual, calendar)
    runners = {
        "arima": lambda: arima.forecast(close, dates, w["arima_bars"], cap, model=model),
        "reversion": lambda: reversion.forecast(close, dates, w["reversion_bars"], bars_per_year(calendar), cap),
        "montecarlo": lambda: montecarlo.forecast(
            close, dates, w["mc_drift_bars"], w["mc_vol_bars"], seed, max_drift=cap
        ),
    }
    out = {}
    last_date = close.index[-1].date()
    for name, run in runners.items():
        try:
            out[name] = sanity_check(run(), float(close.iloc[-1]), last_date)
        except Exception as exc:  # noqa: BLE001 - one failing method must not stop the others
            out[name] = failed(name, dates, f"{type(exc).__name__}: {exc}")
    return out


def consensus(methods: dict[str, MethodForecast], names: tuple[str, ...]):
    ok = [methods[n] for n in names if methods[n].status == "ok"]
    if not ok:
        return None
    return (
        np.mean([m.mid for m in ok], axis=0),
        np.min([m.low for m in ok], axis=0),
        np.max([m.high for m in ok], axis=0),
    )


def to_points(methods: dict[str, MethodForecast], dates, run_date: date) -> list[Point]:
    ok = [n for n in METHODS if methods[n].status == "ok"]
    frame = pd.DataFrame(index=dates)
    for n in ok:
        frame[n], frame[f"{n}_low"], frame[f"{n}_high"] = methods[n].mid, methods[n].low, methods[n].high
    short = consensus(methods, METHODS)
    if short:
        frame["consensus"], frame["consensus_low"], frame["consensus_high"] = short
    long_term = consensus(methods, LONG_TERM_METHODS)
    if long_term:
        frame["long"], frame["long_low"], frame["long_high"] = long_term

    points = []
    short_names = ok + (["consensus"] if short else [])

    daily_end = pd.Timestamp(run_date) + pd.Timedelta(days=DAILY_CALENDAR_DAYS)
    for ts, row in frame[frame.index <= daily_end].iterrows():
        for n in short_names:
            points.append(Point(n, "daily", ts.date(), sig(row[n]), sig(row[f"{n}_low"]), sig(row[f"{n}_high"])))

    in_range = frame[frame.index.year <= MONTHLY_UNTIL]
    for period, g in in_range.groupby(in_range.index.to_period("M")):
        target = period.to_timestamp().date()
        for n in short_names:
            points.append(
                Point(n, "monthly", target, sig(g[n].mean()), sig(g[f"{n}_low"].min()), sig(g[f"{n}_high"].max()))
            )

    long_names = [n for n in LONG_TERM_METHODS if n in ok]
    for year in range(MONTHLY_UNTIL + 1, LAST_YEAR + 1):
        g = frame[frame.index.year == year]
        if g.empty:
            continue
        for n in long_names:
            points.append(
                Point(
                    n,
                    "yearly",
                    date(year, 1, 1),
                    sig(g[n].mean()),
                    sig(g[f"{n}_low"].mean()),
                    sig(g[f"{n}_high"].mean()),
                )
            )
        if long_term:
            points.append(
                Point(
                    "consensus",
                    "yearly",
                    date(year, 1, 1),
                    sig(g["long"].mean()),
                    sig(g["long_low"].mean()),
                    sig(g["long_high"].mean()),
                )
            )
    return points


def jsonable(value):
    """Plain JSON for the database: no numpy types, no NaN (PostgreSQL rejects it)."""
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def build(close: pd.Series, calendar: str, max_annual: float, run_date: date, model=None) -> tuple[list[Point], dict]:
    """Returns (points, method info). `model` reuses a recent ARIMA order instead of searching again."""
    dates = future_dates(close.index[-1].date(), date(LAST_YEAR, 12, 31), calendar)
    methods = run_methods(close, dates, calendar, max_annual, int(run_date.strftime("%Y%m%d")), model)
    info = {n: jsonable({"status": m.status, "error": m.error, "params": m.params}) for n, m in methods.items()}
    return to_points(methods, dates, run_date), info
