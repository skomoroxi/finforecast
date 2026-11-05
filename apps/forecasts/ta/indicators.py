"""Technical indicators on an OHLC DataFrame (columns open, high, low, close), written in pandas.

Each function returns the latest value(s); signal rules live in rules.py so they can be
documented on /methodology/ in one place.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def wilder(s: pd.Series, n: int) -> pd.Series:
    """Wilder's smoothing (an EMA with alpha = 1/n), used by RSI, ATR and ADX."""
    return s.ewm(alpha=1 / n, adjust=False).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi_series(close: pd.Series, n: int = 14) -> pd.Series:
    diff = close.diff()
    gain = wilder(diff.clip(lower=0), n)
    loss = wilder(-diff.clip(upper=0), n)
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100.0).where(loss.notna())


def rsi(df: pd.DataFrame, n: int = 14) -> float:
    return float(rsi_series(df["close"], n).iloc[-1])


def stoch(df: pd.DataFrame, k: int = 9, smooth: int = 6) -> float:
    """Slow %K: the fast %K over `k` bars smoothed with an SMA of `smooth` bars."""
    lo, hi = df["low"].rolling(k).min(), df["high"].rolling(k).max()
    fast = 100 * (df["close"] - lo) / (hi - lo)
    return float(fast.rolling(smooth).mean().iloc[-1])


def stoch_rsi(df: pd.DataFrame, n: int = 14) -> float:
    r = rsi_series(df["close"], n)
    lo, hi = r.rolling(n).min(), r.rolling(n).max()
    return float((100 * (r - lo) / (hi - lo)).iloc[-1])


def macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float]:
    line = ema(df["close"], fast) - ema(df["close"], slow)
    return float(line.iloc[-1]), float(ema(line, signal).iloc[-1])


def adx(df: pd.DataFrame, n: int = 14) -> tuple[float, float, float]:
    """Returns (ADX, +DI, -DI)."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    atr = wilder(true_range(df), n)
    plus_di = 100 * wilder(plus_dm, n) / atr
    minus_di = 100 * wilder(minus_dm, n) / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    return float(wilder(dx, n).iloc[-1]), float(plus_di.iloc[-1]), float(minus_di.iloc[-1])


def williams_r(df: pd.DataFrame, n: int = 14) -> float:
    hi, lo = df["high"].rolling(n).max(), df["low"].rolling(n).min()
    return float((-100 * (hi - df["close"]) / (hi - lo)).iloc[-1])


def cci(df: pd.DataFrame, n: int = 14) -> float:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma = tp.rolling(n).mean()
    mad = tp.rolling(n).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    return float(((tp - sma) / (0.015 * mad)).iloc[-1])


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift()
    return pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> tuple[float, float]:
    """Returns (ATR, its own n-bar average): ATR above its average means rising volatility."""
    a = wilder(true_range(df), n)
    return float(a.iloc[-1]), float(a.rolling(n).mean().iloc[-1])


def highs_lows(df: pd.DataFrame, n: int = 14) -> float:
    """Average distance of the bar's high and low from the n-bar extremes (≥0 buy, ≤0 sell)."""
    hi, lo = df["high"].rolling(n).max(), df["low"].rolling(n).min()
    return float((((df["high"] - hi) + (df["low"] - lo)) / 2).iloc[-1])


def ultimate_oscillator(df: pd.DataFrame, s: int = 7, m: int = 14, long_bars: int = 28) -> float:
    prev = df["close"].shift()
    bp = df["close"] - pd.concat([df["low"], prev], axis=1).min(axis=1)
    tr = pd.concat([df["high"], prev], axis=1).max(axis=1) - pd.concat([df["low"], prev], axis=1).min(axis=1)
    avg = lambda n: bp.rolling(n).sum() / tr.rolling(n).sum()  # noqa: E731
    return float((100 * (4 * avg(s) + 2 * avg(m) + avg(long_bars)) / 7).iloc[-1])


def roc(df: pd.DataFrame, n: int = 12) -> float:
    return float((100 * (df["close"] / df["close"].shift(n) - 1)).iloc[-1])


def bull_bear_power(df: pd.DataFrame, n: int = 13) -> float:
    e = ema(df["close"], n)
    return float(((df["high"] - e) + (df["low"] - e)).iloc[-1])


def sma_last(close: pd.Series, n: int) -> float | None:
    return float(close.rolling(n).mean().iloc[-1]) if len(close) >= n else None


def ema_last(close: pd.Series, n: int) -> float | None:
    return float(ema(close, n).iloc[-1]) if len(close) >= n else None


def pivots(prev: pd.Series) -> dict[str, dict[str, float]]:
    """Pivot levels from the previous completed period's open/high/low/close."""
    o, h, low, c = prev["open"], prev["high"], prev["low"], prev["close"]
    r = h - low
    p = (h + low + c) / 3
    classic = {
        "s3": low - 2 * (h - p),
        "s2": p - r,
        "s1": 2 * p - h,
        "p": p,
        "r1": 2 * p - low,
        "r2": p + r,
        "r3": h + 2 * (p - low),
    }
    fib = {
        "s3": p - r,
        "s2": p - 0.618 * r,
        "s1": p - 0.382 * r,
        "p": p,
        "r1": p + 0.382 * r,
        "r2": p + 0.618 * r,
        "r3": p + r,
    }
    cam = {
        "s3": c - r * 1.1 / 4,
        "s2": c - r * 1.1 / 6,
        "s1": c - r * 1.1 / 12,
        "p": p,
        "r1": c + r * 1.1 / 12,
        "r2": c + r * 1.1 / 6,
        "r3": c + r * 1.1 / 4,
    }
    wp = (h + low + 2 * c) / 4
    woodie = {
        "s3": low - 2 * (h - wp),
        "s2": wp - r,
        "s1": 2 * wp - h,
        "p": wp,
        "r1": 2 * wp - low,
        "r2": wp + r,
        "r3": h + 2 * (wp - low),
    }
    x = h + 2 * low + c if c < o else (2 * h + low + c if c > o else h + low + 2 * c)
    demark = {"s1": x / 2 - h, "p": x / 4, "r1": x / 2 - low}
    rnd = lambda d: {k: float(v) for k, v in d.items()}  # noqa: E731
    return {
        "classic": rnd(classic),
        "fibonacci": rnd(fib),
        "camarilla": rnd(cam),
        "woodie": rnd(woodie),
        "demark": rnd(demark),
    }
