"""Technical analysis for one asset: oscillators, moving averages, pivots and summaries per timeframe.

Close-only assets (oil, heating oil) show only what a close can support; indicators and pivots that
need the day's high and low are left out, and `ohlc_basis` says so (TECHNICAL-TASK §4).
"""

import pandas as pd

from ..engine.build import sig
from . import indicators as ind
from . import rules

MA_PERIODS = (5, 10, 20, 50, 100, 200)
TIMEFRAMES = {"daily": None, "weekly": "W-FRI", "monthly": "ME"}
RECENT = 300  # bars that decide whether an asset has real ranges
ORDER = (
    "rsi_14",
    "stoch_9_6",
    "stochrsi_14",
    "macd_12_26",
    "adx_14",
    "williams_r_14",
    "cci_14",
    "atr_14",
    "highs_lows_14",
    "ultimate_oscillator",
    "roc_12",
    "bull_bear_power_13",
)


def resample(df: pd.DataFrame, rule: str | None) -> pd.DataFrame:
    if rule is None:
        return df
    # The latest week or month is still in progress; it is included, as on most TA dashboards.
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    return df.resample(rule).agg(agg).dropna(subset=["close"])


def _r(x: float | None) -> float | None:
    return None if x is None or pd.isna(x) else sig(x)


def has_ranges(df: pd.DataFrame) -> bool:
    return df["high"].tail(RECENT).notna().mean() > 0.5


def fill_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """A few bars without a range (a missing proxy day) borrow the close, so indicators stay defined."""
    return df.assign(
        open=df["open"].fillna(df["close"]), high=df["high"].fillna(df["close"]), low=df["low"].fillna(df["close"])
    )


def analyse(df: pd.DataFrame, period_complete: bool, ranges: bool) -> dict:
    """period_complete: the last bar is a finished period (daily); weekly and monthly bars are in progress."""
    close = float(df["close"].iloc[-1])
    macd_line, macd_signal = ind.macd(df)
    values = {
        "rsi_14": (ind.rsi(df), lambda v: rules.zone(v, 50, 30, 70), {}),
        "stochrsi_14": (ind.stoch_rsi(df), lambda v: rules.zone(v, 50, 20, 80), {}),
        "macd_12_26": (macd_line, rules.sign, {"signal_line": _r(macd_signal)}),
        "roc_12": (ind.roc(df), rules.sign, {}),
    }
    if ranges:
        adx, plus_di, minus_di = ind.adx(df)
        atr, atr_avg = ind.atr(df)
        values |= {
            "stoch_9_6": (ind.stoch(df), lambda v: rules.zone(v, 50, 20, 80), {}),
            "adx_14": (
                adx,
                lambda v: rules.adx_action(v, plus_di, minus_di),
                {"plus_di": _r(plus_di), "minus_di": _r(minus_di)},
            ),
            "williams_r_14": (ind.williams_r(df), lambda v: rules.zone(v, -50, -80, -20), {}),
            "cci_14": (ind.cci(df), lambda v: rules.zone(v, 0, -200, 200), {}),
            "atr_14": (atr, lambda v: rules.atr_action(v, atr_avg), {}),
            "highs_lows_14": (ind.highs_lows(df), rules.sign, {}),
            "ultimate_oscillator": (ind.ultimate_oscillator(df), lambda v: rules.zone(v, 50, 30, 70), {}),
            "bull_bear_power_13": (ind.bull_bear_power(df), rules.sign, {}),
        }

    oscillators = []
    counts = {"buy": 0, "sell": 0, "neutral": 0}
    for name in (n for n in ORDER if n in values):
        value, rule, extra = values[name]
        action = rule(value)
        oscillators.append({"name": name, "value": _r(value), "action": action} | extra)
        if name == "atr_14":
            continue  # a volatility measure has no direction
        counts["buy" if action == rules.BUY else "sell" if action == rules.SELL else "neutral"] += 1

    mas = []
    ma_counts = {"buy": 0, "sell": 0, "neutral": 0}
    for n in MA_PERIODS:
        row = {"period": n}
        for kind, fn in (("simple", ind.sma_last), ("exponential", ind.ema_last)):
            v = fn(df["close"], n)
            action = rules.price_vs_ma(close, v)
            row[kind] = {"value": _r(v), "action": action}
            if action:
                ma_counts[action] += 1
        mas.append(row)

    pivots = {}
    if ranges and len(df) >= 2:
        # Pivots for the coming or current period come from the last finished one.
        source = df.iloc[-1] if period_complete else df.iloc[-2]
        pivots = {kind: {k: _r(v) for k, v in levels.items()} for kind, levels in ind.pivots(source).items()}

    total = {k: counts[k] + ma_counts[k] for k in counts}
    return {
        "bar_date": df.index[-1].date().isoformat(),
        "close": _r(close),
        "oscillators": oscillators,
        "moving_averages": mas,
        "pivots": pivots,
        "summary": {
            "oscillators": counts | {"verdict": rules.verdict(**counts)},
            "moving_averages": ma_counts | {"verdict": rules.verdict(**ma_counts)},
            "overall": total | {"verdict": rules.verdict(**total)},
        },
    }


def build(df: pd.DataFrame) -> dict:
    """`df` has float columns open, high, low, close (NaN where unknown) on a date index."""
    ranges = has_ranges(df)
    data = fill_gaps(df) if ranges else df
    out = {}
    for name, rule in TIMEFRAMES.items():
        bars = resample(data, rule)
        if len(bars) >= 2:
            out[name] = analyse(bars, rule is None, ranges)
    return out
