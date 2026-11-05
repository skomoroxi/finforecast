"""Provider registry. API keys come from settings (environment) only."""

from django.conf import settings

from .alphavantage import AlphaVantageSource
from .base import Bar, SourceError
from .binance import BinanceSource
from .finnhub import FinnhubSource
from .fred import FredSource
from .twelvedata import TwelveDataSource

__all__ = ["Bar", "SourceError", "finnhub", "get_source"]


def _keyed(cls, setting: str):
    key = getattr(settings, setting)
    if not key:
        raise SourceError(f"{setting} is not set")
    return cls(key)


def get_source(name: str):
    if name == "twelvedata":
        return _keyed(TwelveDataSource, "TWELVEDATA_API_KEY")
    if name == "alphavantage":
        return _keyed(AlphaVantageSource, "ALPHAVANTAGE_API_KEY")
    if name == "fred":
        return _keyed(FredSource, "FRED_API_KEY")
    if name == "binance":
        return BinanceSource()
    raise SourceError(f"unknown source {name!r}")


def finnhub() -> FinnhubSource:
    return _keyed(FinnhubSource, "FINNHUB_API_KEY")
