"""Binance public market data (no key): coins Twelve Data lacks, and the crypto fallback."""

from datetime import UTC, datetime
from decimal import Decimal

from .base import Bar, HttpSource, SourceError

URL = "https://data-api.binance.vision/api/v3/klines"
PAGE = 1000
DAY_MS = 86_400_000


class BinanceSource(HttpSource):
    name = "binance"

    def daily_bars(self, symbol: str, count: int) -> list[Bar]:
        if count <= PAGE:
            bars = self._page(symbol, count)
        else:
            bars = []
            start = 0
            while True:  # oldest first, page by page
                page = self._page(symbol, PAGE, start)
                bars += page
                if len(page) < PAGE:
                    break
                last_day = datetime(page[-1].date.year, page[-1].date.month, page[-1].date.day, tzinfo=UTC)
                start = int(last_day.timestamp() * 1000) + DAY_MS
            bars = bars[-count:]
        if not bars:
            raise SourceError(f"binance returned no bars for {symbol}")
        return bars

    def _page(self, symbol: str, limit: int, start: int | None = None) -> list[Bar]:
        params = {"symbol": symbol, "interval": "1d", "limit": limit}
        if start is not None:
            params["startTime"] = start
        return self._get(URL, params, self._parse)

    def _parse(self, response) -> list[Bar]:
        payload = response.json()
        if isinstance(payload, dict):
            raise SourceError(self._clean(f"binance {payload.get('code')}: {payload.get('msg')}"))
        return [
            Bar(
                date=datetime.fromtimestamp(k[0] / 1000, UTC).date(),
                open=Decimal(k[1]),
                high=Decimal(k[2]),
                low=Decimal(k[3]),
                close=Decimal(k[4]),
                volume=float(k[5]),
            )
            for k in payload
        ]
