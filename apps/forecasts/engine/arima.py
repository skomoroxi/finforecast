"""M1: ARIMA(p,1,q) on log prices. Order and drift (on/off) are chosen by AIC."""

from __future__ import annotations

import warnings
from datetime import date

import numpy as np
from statsmodels.tsa.arima.model import ARIMA

from .common import INTERVAL, MethodForecast

MAX_P = 3
MAX_Q = 3


def _fit(y: np.ndarray, order: tuple[int, int, int], trend: str):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ARIMA(y, order=order, trend=trend).fit()


def select_model(y: np.ndarray) -> tuple[tuple[int, int, int], str]:
    """Grid over p, q in 0..3 and trend in {none, drift}; lowest AIC wins."""
    best, best_aic = ((0, 1, 0), "n"), np.inf
    for trend in ("n", "t"):
        for p in range(MAX_P + 1):
            for q in range(MAX_Q + 1):
                try:
                    res = _fit(y, (p, 1, q), trend)
                except Exception:  # noqa: BLE001 - a failed candidate is simply skipped
                    continue
                if np.isfinite(res.aic) and res.aic < best_aic:
                    best, best_aic = ((p, 1, q), trend), res.aic
    return best


def predict_log(y: np.ndarray, order: tuple[int, int, int], trend: str, steps: int):
    fc = _fit(y, order, trend).get_forecast(steps=steps)
    ci = np.asarray(fc.conf_int(alpha=1 - INTERVAL))
    return np.asarray(fc.predicted_mean), ci[:, 0], ci[:, 1]


def forecast(close, dates, window_bars: int, max_drift: float | None = None, model=None) -> MethodForecast:
    """`model` is (order, trend, selected_on) from a recent run; without it the order search runs."""
    y = np.log(close.to_numpy()[-window_bars:])
    if model:
        order, trend, selected_on = model
    else:
        order, trend = select_model(y)
        selected_on = date.today().isoformat()
    model_drift = trend == "t"
    mid, low, high = predict_log(y, order, trend, len(dates))
    drift_dropped = False
    if trend == "t" and max_drift is not None and abs(mid[-1] - y[-1]) / len(dates) > max_drift:
        # The fitted drift is steeper than the growth cap: use the same order without drift.
        trend, drift_dropped = "n", True
        mid, low, high = predict_log(y, order, trend, len(dates))
    return MethodForecast(
        "arima",
        dates,
        np.exp(mid),
        np.exp(low),
        np.exp(high),
        params={
            "order": list(order),
            "drift": trend == "t",
            "model_drift": model_drift,
            "drift_dropped_by_cap": drift_dropped,
            "window_bars": len(y),
            "selected_on": selected_on,
        },
    )
