"""Twelve Data: US shares and ETFs, OTC ADRs, FX, most crypto, gold."""

from datetime import date
from decimal import Decimal

from .base import Bar, HttpSource, Retry, SourceError

URL = "https://api.twelvedata.com/time_series"
MAX_OUTPUTSIZE = 5000


class TwelveDataSource(HttpSource):
    name = "twelvedata"
    backoff = 15.0

    def daily_bars(self, symbol: str, count: int) -> list[Bar]:
        params = {
            "symbol": symbol,
            "interval": "1day",
            "outputsize": min(count, MAX_OUTPUTSIZE),
            "order": "asc",
            "timezone": "UTC",
            "apikey": self._api_key,
        }
        return self._get(URL, params, lambda r: self._parse(r, symbol))

    def _parse(self, response, symbol: str) -> list[Bar]:
        payload = response.json()
        if payload.get("status") == "error":
            if payload.get("code") == 429:
                raise Retry("rate limited")
            raise SourceError(self._clean(f"twelvedata {payload.get('code')}: {payload.get('message')}"))
        values = payload.get("values")
        if not values:
            raise SourceError(f"twelvedata returned no values for {symbol}")
        return [
            Bar(
                date=date.fromisoformat(v["datetime"][:10]),
                open=Decimal(v["open"]),
                high=Decimal(v["high"]),
                low=Decimal(v["low"]),
                close=Decimal(v["close"]),
                volume=float(v["volume"]) if v.get("volume") not in (None, "") else None,
            )
            for v in values
        ]
