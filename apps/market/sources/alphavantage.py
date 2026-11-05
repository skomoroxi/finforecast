"""Alpha Vantage: silver, WTI and Brent, and the last 100 XETRA closes (25 requests a day).

The symbol picks the endpoint: SILVER/GOLD, WTI/BRENT, anything else is a share such as BMW.DEX.
"""

from datetime import date
from decimal import Decimal

from .base import Bar, HttpSource, Retry, SourceError

URL = "https://www.alphavantage.co/query"
METALS = {"SILVER", "GOLD"}
ENERGY = {"WTI", "BRENT"}


class AlphaVantageSource(HttpSource):
    name = "alphavantage"
    timeout = 60
    retries = 2
    backoff = 3.0

    def daily_bars(self, symbol: str, count: int) -> list[Bar]:
        params = {"apikey": self._api_key}
        if symbol in METALS:
            params |= {"function": "GOLD_SILVER_HISTORY", "symbol": symbol, "interval": "daily"}
        elif symbol in ENERGY:
            params |= {"function": symbol, "interval": "daily"}
        else:
            params |= {"function": "TIME_SERIES_DAILY", "symbol": symbol}
        bars = self._get(URL, params, self._parse)
        if not bars:
            raise SourceError(f"alphavantage returned no data for {symbol}")
        return sorted(bars, key=lambda b: b.date)[-count:]

    def _parse(self, response) -> list[Bar]:
        payload = response.json()
        # Problems arrive as HTTP 200 with one of these keys; some of them quote the API key.
        if "Error Message" in payload:
            raise SourceError(self._clean(f"alphavantage: {payload['Error Message']}"))
        message = payload.get("Information") or payload.get("Note")
        if message:
            raise Retry(message[:160])
        if "Time Series (Daily)" in payload:
            return [
                Bar(
                    date=date.fromisoformat(day),
                    open=Decimal(row["1. open"]),
                    high=Decimal(row["2. high"]),
                    low=Decimal(row["3. low"]),
                    close=Decimal(row["4. close"]),
                    volume=float(row["5. volume"]),
                )
                for day, row in payload["Time Series (Daily)"].items()
            ]
        bars = []
        for row in payload.get("data") or []:
            value = row.get("price", row.get("value"))
            if value not in (None, "", "."):  # "." marks a day without a price
                bars.append(Bar(date=date.fromisoformat(row["date"]), close=Decimal(value), basis="close"))
        return bars
