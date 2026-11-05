"""Kraken public market data (no key): coins Binance stopped listing. Returns at most the last 720 days."""

from datetime import UTC, datetime
from decimal import Decimal

from .base import Bar, HttpSource, SourceError

URL = "https://api.kraken.com/0/public/OHLC"


class KrakenSource(HttpSource):
    name = "kraken"

    def daily_bars(self, symbol: str, count: int) -> list[Bar]:
        bars = self._get(URL, {"pair": symbol, "interval": 1440}, self._parse)
        if not bars:
            raise SourceError(f"kraken returned no bars for {symbol}")
        return bars[-count:]

    def _parse(self, response) -> list[Bar]:
        payload = response.json()
        if payload.get("error"):
            raise SourceError(self._clean(f"kraken: {payload['error']}"))
        rows = next(v for k, v in payload["result"].items() if k != "last")
        return [
            Bar(
                date=datetime.fromtimestamp(r[0], UTC).date(),
                open=Decimal(r[1]),
                high=Decimal(r[2]),
                low=Decimal(r[3]),
                close=Decimal(r[4]),
                volume=float(r[6]),
            )
            for r in rows
        ]
