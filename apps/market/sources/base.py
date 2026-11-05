"""Common shape of a daily bar and the HTTP plumbing every provider adapter shares."""

import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import requests

from apps.market import ratelimit


class SourceError(RuntimeError):
    """The provider failed or returned unusable data."""


class Retry(Exception):
    """A temporary problem found in a response body; worth another attempt."""


@dataclass(frozen=True)
class Bar:
    date: date
    close: Decimal
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    volume: float | None = None
    basis: str = "full"


class HttpSource:
    """GET with pacing, retries and error messages that never contain the API key."""

    name = ""
    timeout = 30
    retries = 3
    backoff = 5.0

    def __init__(self, api_key: str = "", session: requests.Session | None = None, pace: bool = True):
        self._api_key = api_key
        self._session = session or requests.Session()
        self._pace = pace  # tests turn pacing and sleeps off

    def _clean(self, text: object) -> str:
        text = str(text)
        return text.replace(self._api_key, "***") if self._api_key else text

    def _get(self, url: str, params: dict, parse):
        """Return `parse(response)` for a successful response, retrying transient failures."""
        last_error = ""
        for attempt in range(self.retries):
            if self._pace:
                try:
                    ratelimit.acquire(self.name)
                except ratelimit.BudgetExceeded as exc:
                    raise SourceError(str(exc)) from None
            try:
                response = self._session.get(url, params=params, timeout=self.timeout)
                if response.status_code == 429 or response.status_code >= 500:
                    raise Retry(f"HTTP {response.status_code}")
                return parse(response)
            except requests.RequestException as exc:
                last_error = type(exc).__name__  # str(exc) would contain the URL and so the key
            except Retry as exc:
                last_error = self._clean(exc)
            except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
                raise SourceError(f"{self.name}: unexpected response ({type(exc).__name__})") from None
            if attempt < self.retries - 1 and self._pace:
                time.sleep(self.backoff * (attempt + 1))
        raise SourceError(f"{self.name}: failed after {self.retries} attempts: {last_error}")
