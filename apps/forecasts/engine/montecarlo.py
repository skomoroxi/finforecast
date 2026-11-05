"""M3: Monte Carlo simulation of geometric Brownian motion.

Drift comes from a long window of daily log returns, volatility from a short one. Paths are
simulated step by step, so memory stays at one vector of PATHS values however long the horizon.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .common import INTERVAL, MethodForecast

PATHS = 10_000


def estimate(close: pd.Series, drift_bars: int, vol_bars: int, max_drift: float | None = None) -> tuple[float, float]:
    """(mu, sigma) of daily log returns; mu is clipped to ±max_drift when a cap is given."""
    r = np.diff(np.log(close.to_numpy()))
    mu = float(r[-drift_bars:].mean())
    if max_drift is not None:
        mu = float(np.clip(mu, -max_drift, max_drift))
    return mu, float(r[-vol_bars:].std(ddof=1))


def median_path(last_close: float, mu: float, steps: int) -> np.ndarray:
    """Median of log-normal GBM at each step: used by the backtest instead of a full simulation."""
    return last_close * np.exp(mu * np.arange(1, steps + 1))


def forecast(
    close: pd.Series,
    dates: pd.DatetimeIndex,
    drift_bars: int,
    vol_bars: int,
    seed: int,
    paths: int = PATHS,
    max_drift: float | None = None,
) -> MethodForecast:
    raw_mu, _ = estimate(close, drift_bars, vol_bars)
    mu, sigma = estimate(close, drift_bars, vol_bars, max_drift)
    rng = np.random.default_rng(seed)
    tail = (1 - INTERVAL) / 2
    x = np.zeros(paths)
    q = np.empty((len(dates), 3))
    for i in range(len(dates)):
        x += mu + sigma * rng.standard_normal(paths)
        q[i] = np.quantile(x, [tail, 0.5, 1 - tail])
    s0 = float(close.iloc[-1])
    return MethodForecast(
        "montecarlo",
        dates,
        s0 * np.exp(q[:, 1]),
        s0 * np.exp(q[:, 0]),
        s0 * np.exp(q[:, 2]),
        params={
            "mu_daily": round(mu, 6),
            "mu_daily_raw": round(raw_mu, 6),
            "drift_capped": mu != raw_mu,
            "sigma_daily": round(sigma, 6),
            "paths": paths,
            "drift_bars": drift_bars,
            "vol_bars": vol_bars,
        },
    )
