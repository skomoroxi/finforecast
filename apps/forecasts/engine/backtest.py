"""Walk-forward backtest: refit at past dates on data up to that day only, compare with what happened.

Shown until a page has 30 real matured forecasts (TECHNICAL-TASK §11).
"""

import numpy as np
import pandas as pd

from . import arima, montecarlo, reversion

# Horizon label to bars ahead, per calendar. 7 and 30 calendar days are about 5 and 21 trading days.
HORIZONS = {
    "fx": {"1d": 1, "7d": 5, "30d": 21},
    "nyse": {"1d": 1, "7d": 5, "30d": 21},
    "crypto": {"1d": 1, "7d": 7, "30d": 30},
}
MIN_TRAIN_BARS = 250  # young assets still get a backtest, on what history they have


def walk_forward(close: pd.Series, calendar: str, windows: dict, max_drift: float, model, origins=50, step=5) -> list:
    """Rows of {method, horizon, mape, mae, direction_pct, bias_pct, samples}. Empty if history is too short."""
    horizons = HORIZONS[calendar]
    longest = max(horizons.values())
    values = close.to_numpy()
    last_origin = len(values) - 1 - longest
    start = min(windows["arima_bars"], MIN_TRAIN_BARS)
    origin_idx = [last_origin - k * step for k in range(origins) if last_origin - k * step > start]
    if not origin_idx:
        return []

    order, trend = model
    names = ("arima", "reversion", "montecarlo", "consensus")
    records = {m: {h: [] for h in horizons} for m in names}
    for i in origin_idx:
        train = values[: i + 1]
        log_train = np.log(train)
        mu, _ = montecarlo.estimate(pd.Series(train), windows["mc_drift_bars"], windows["mc_vol_bars"], max_drift)
        arima_window = log_train[-windows["arima_bars"] :]
        reversion_fit = reversion.fit(log_train[-windows["reversion_bars"] :], max_drift)
        paths = {
            "arima": np.exp(arima.predict_log(arima_window, tuple(order), trend, longest)[0]),
            "reversion": np.exp(reversion.predict_log(reversion_fit, longest, max_drift)[0]),
            "montecarlo": montecarlo.median_path(train[-1], mu, longest),
        }
        paths["consensus"] = np.mean([paths["arima"], paths["reversion"], paths["montecarlo"]], axis=0)
        for label, h in horizons.items():
            actual = values[i + h]
            for method, path in paths.items():
                records[method][label].append((path[h - 1], actual, train[-1]))

    rows = []
    for method, by_horizon in records.items():
        for label, triples in by_horizon.items():
            f, a, base = (np.array(x, dtype=float) for x in zip(*triples, strict=True))
            rows.append(
                {
                    "method": method,
                    "horizon": label,
                    "mape": float(np.mean(np.abs(f / a - 1)) * 100),
                    "mae": float(np.mean(np.abs(f - a))),
                    "direction_pct": float(np.mean(np.sign(f - base) == np.sign(a - base)) * 100),
                    "bias_pct": float(np.mean(f / a - 1) * 100),
                    "samples": len(triples),
                }
            )
    return rows
