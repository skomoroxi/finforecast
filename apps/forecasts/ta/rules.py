"""Signal rules for the technical summary. Shown on /methodology/; change them only here.

Oscillators with overbought/oversold zones: inside a zone the action is "overbought" /
"oversold" (counted as neutral); otherwise above the midline is buy, below is sell.
"""

from __future__ import annotations

import math

BUY, SELL, NEUTRAL = "buy", "sell", "neutral"
OVERBOUGHT, OVERSOLD = "overbought", "oversold"


def zone(value: float, mid: float, low: float, high: float) -> str:
    if math.isnan(value):
        return NEUTRAL
    if value > high:
        return OVERBOUGHT
    if value < low:
        return OVERSOLD
    return BUY if value > mid else SELL if value < mid else NEUTRAL


def sign(value: float) -> str:
    if math.isnan(value):
        return NEUTRAL
    return BUY if value > 0 else SELL if value < 0 else NEUTRAL


def adx_action(adx: float, plus_di: float, minus_di: float, threshold: float = 25) -> str:
    """A trend counts only when ADX is above the threshold; its direction comes from the DI lines."""
    if math.isnan(adx) or adx < threshold:
        return NEUTRAL
    return BUY if plus_di > minus_di else SELL


def atr_action(atr: float, atr_avg: float) -> str:
    return "high_volatility" if atr > atr_avg else "low_volatility"


def price_vs_ma(close: float, ma: float | None) -> str | None:
    if ma is None:
        return None
    return BUY if close > ma else SELL if close < ma else NEUTRAL


def verdict(buy: int, sell: int, neutral: int) -> str:
    total = buy + sell + neutral
    if total == 0:
        return "neutral"
    score = (buy - sell) / total
    if score <= -0.5:
        return "strong_sell"
    if score < -0.1:
        return "sell"
    if score <= 0.1:
        return "neutral"
    if score < 0.5:
        return "buy"
    return "strong_buy"
