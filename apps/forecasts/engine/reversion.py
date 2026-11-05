"""M2: long-run trend with mean reversion.

log(price) = a + b·t + e_t, where the deviation e_t from the linear trend follows an AR(1)
(the discrete form of an Ornstein-Uhlenbeck process): e_t = φ·e_(t-1) + ε_t.
The forecast moves from today's deviation back toward the trend line with half-life
ln(0.5) / ln(φ) bars, and the interval widens toward the deviation's long-run spread.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .common import INTERVAL, MethodForecast

Z80 = 1.2815515655446004  # standard normal quantile for a two-sided 80% interval
MAX_PHI = 0.9995  # keeps the process stationary if the fit lands at a unit root


def fit(y: np.ndarray, max_slope: float | None = None) -> dict:
    """max_slope caps the trend (log per bar); the intercept is then refit for the capped slope."""
    t = np.arange(len(y), dtype=float)
    b, a = np.polyfit(t, y, 1)
    raw_b = float(b)
    if max_slope is not None and abs(b) > max_slope:
        b = float(np.sign(b) * max_slope)
        a = float(np.mean(y - b * t))
    e = y - (a + b * t)
    phi = float(np.dot(e[1:], e[:-1]) / np.dot(e[:-1], e[:-1]))
    phi = min(max(phi, 0.0), MAX_PHI)
    sigma = float(np.std(e[1:] - phi * e[:-1], ddof=1))
    return {
        "a": float(a),
        "b": float(b),
        "raw_b": raw_b,
        "phi": phi,
        "sigma": sigma,
        "e_last": float(e[-1]),
        "n": len(y),
    }


def predict_log(p: dict, steps: int, max_slope: float | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    h = np.arange(1, steps + 1)
    decay = p["phi"] ** h
    mid = p["a"] + p["b"] * (p["n"] - 1 + h) + decay * p["e_last"]
    sd = p["sigma"] * np.sqrt((1 - decay**2) / (1 - p["phi"] ** 2))
    z = Z80 if INTERVAL == 0.8 else float(np.sqrt(2) * _erfinv(INTERVAL))
    if max_slope is not None:
        # The cap binds the path, not only the trend: a price far below its trend line
        # must not climb back faster than the cap allows.
        last = p["a"] + p["b"] * (p["n"] - 1) + p["e_last"]
        mid = np.clip(mid, last - max_slope * h, last + max_slope * h)
    return mid, mid - z * sd, mid + z * sd


def _erfinv(x: float) -> float:  # only needed if INTERVAL is ever changed from 0.8
    from statistics import NormalDist

    return NormalDist().inv_cdf((1 + x) / 2) / np.sqrt(2)


def forecast(
    close: pd.Series, dates: pd.DatetimeIndex, window_bars: int, bars_per_year: int, max_slope: float | None = None
) -> MethodForecast:
    y = np.log(close.to_numpy()[-window_bars:])
    p = fit(y, max_slope)
    mid, low, high = predict_log(p, len(dates), max_slope)
    half_life = np.log(0.5) / np.log(p["phi"]) if 0 < p["phi"] < 1 else None
    return MethodForecast(
        "reversion",
        dates,
        np.exp(mid),
        np.exp(low),
        np.exp(high),
        params={
            "trend_annual_pct": round((np.exp(p["b"] * bars_per_year) - 1) * 100, 2),
            "trend_annual_pct_raw": round((np.exp(p["raw_b"] * bars_per_year) - 1) * 100, 2),
            "trend_capped": p["b"] != p["raw_b"],
            "deviation_from_trend_pct": round((np.exp(p["e_last"]) - 1) * 100, 2),
            "phi": round(p["phi"], 5),
            "half_life_bars": round(half_life, 1) if half_life else None,
            "window_bars": p["n"],
        },
    )
