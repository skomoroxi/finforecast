"""Finnhub: delayed live quotes for US-traded shares and ETFs (TECHNICAL-TASK §3.4)."""

from .base import HttpSource, SourceError

URL = "https://finnhub.io/api/v1/quote"


class FinnhubSource(HttpSource):
    name = "finnhub"
    timeout = 15
    retries = 2

    def quote(self, symbol: str) -> dict:
        return self._get(URL, {"symbol": symbol, "token": self._api_key}, lambda r: self._parse(r, symbol))

    def _parse(self, response, symbol: str) -> dict:
        payload = response.json()
        if not payload.get("c"):  # an unknown symbol comes back as zeros
            raise SourceError(f"finnhub has no quote for {symbol}")
        return {"price": payload["c"], "change_pct": payload.get("dp"), "time": payload.get("t")}
