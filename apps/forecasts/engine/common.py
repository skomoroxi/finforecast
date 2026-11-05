"""Shared types and helpers for the forecast methods (TECHNICAL-TASK §5.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

INTERVAL = 0.8  # all methods report an 80% interval (P10–P90)


@dataclass
class MethodForecast:
    """One method's path over the forecast dates, in price units (not logs)."""

    name: str
    dates: pd.DatetimeIndex
    mid: np.ndarray
    low: np.ndarray
    high: np.ndarray
    params: dict = field(default_factory=dict)
    status: str = "ok"
    error: str | None = None


def future_dates(last: date, end: date, calendar: str) -> pd.DatetimeIndex:
    """Trading dates after `last` up to and including `end` for the asset's calendar."""
    start = pd.Timestamp(last) + pd.Timedelta(days=1)
    if calendar == "crypto":
        return pd.date_range(start, end, freq="D")
    # fx: Mon–Fri. nyse: Mon–Fri too; exchange holidays are ignored for the MVP.
    return pd.bdate_range(start, end)


def bars_per_year(calendar: str) -> int:
    return 365 if calendar == "crypto" else 261


def daily_drift_cap(max_annual: float, calendar: str) -> float:
    """Largest allowed drift per bar in log terms, from an annual cap such as 0.25 (= ±25%/year)."""
    return float(np.log1p(max_annual) / bars_per_year(calendar))


def sanity_check(fc: MethodForecast, last_close: float, last_date: date, years: int = 5) -> MethodForecast:
    """Fail the method if its path is not finite or leaves [0.1x, 10x] of today's price within `years`."""
    arrays = np.concatenate([fc.mid, fc.low, fc.high])
    if not np.all(np.isfinite(arrays)):
        fc.status, fc.error = "failed", "non-finite values"
        return fc
    horizon = fc.dates <= pd.Timestamp(last_date) + pd.DateOffset(years=years)
    ratio = fc.mid[horizon] / last_close
    if ratio.size and (ratio.min() < 0.1 or ratio.max() > 10):
        fc.status, fc.error = "failed", f"path outside 0.1x–10x of last close within {years} years"
    return fc


def failed(name: str, dates: pd.DatetimeIndex, error: str) -> MethodForecast:
    empty = np.full(len(dates), np.nan)
    return MethodForecast(name, dates, empty, empty, empty, status="failed", error=error)
