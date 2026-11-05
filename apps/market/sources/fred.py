"""FRED: EIA's New York Harbor heating oil series. EIA's own API refuses this server's IP range."""

from datetime import date
from decimal import Decimal

from .base import Bar, HttpSource, SourceError

URL = "https://api.stlouisfed.org/fred/series/observations"


class FredSource(HttpSource):
    name = "fred"

    def daily_bars(self, symbol: str, count: int) -> list[Bar]:
        params = {
            "series_id": symbol,
            "api_key": self._api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": min(count, 100_000),
        }
        bars = self._get(URL, params, self._parse)
        if not bars:
            raise SourceError(f"fred returned no data for {symbol}")
        return sorted(bars, key=lambda b: b.date)

    def _parse(self, response) -> list[Bar]:
        payload = response.json()
        if "error_message" in payload:
            raise SourceError(self._clean(f"fred: {payload['error_message']}"))
        return [
            Bar(date=date.fromisoformat(o["date"]), close=Decimal(o["value"]), basis="close")
            for o in payload["observations"]
            if o["value"] not in ("", ".")
        ]
