from datetime import date
from decimal import Decimal

import pytest
import requests

from apps.market.sources.alphavantage import AlphaVantageSource
from apps.market.sources.base import SourceError
from apps.market.sources.binance import BinanceSource
from apps.market.sources.finnhub import FinnhubSource
from apps.market.sources.fred import FredSource
from apps.market.sources.kraken import KrakenSource
from apps.market.sources.twelvedata import TwelveDataSource

from .fakes import FakeResponse, FakeSession

KEY = "secret-key-123"


def td_value(day="2026-11-03"):
    return {"datetime": day, "open": "1.5", "high": "2", "low": "1", "close": "1.75", "volume": "100"}


def test_twelvedata_parses_bars():
    session = FakeSession(FakeResponse({"values": [td_value()]}))
    bars = TwelveDataSource(KEY, session, pace=False).daily_bars("AAPL", 5)
    assert bars[0].date == date(2026, 11, 3)
    assert bars[0].close == Decimal("1.75")
    assert bars[0].volume == 100.0
    assert session.calls[0]["outputsize"] == 5


def test_twelvedata_fx_has_no_volume():
    value = td_value()
    del value["volume"]
    bars = TwelveDataSource(KEY, FakeSession(FakeResponse({"values": [value]})), pace=False).daily_bars("EUR/USD", 1)
    assert bars[0].volume is None


def test_twelvedata_retries_rate_limit():
    session = FakeSession(
        FakeResponse({"status": "error", "code": 429, "message": "slow down"}, 429),
        FakeResponse({"values": [td_value()]}),
    )
    assert TwelveDataSource(KEY, session, pace=False).daily_bars("AAPL", 1)
    assert len(session.calls) == 2


def test_twelvedata_error_never_contains_the_key():
    payload = {"status": "error", "code": 401, "message": f"bad key {KEY}"}
    with pytest.raises(SourceError) as exc:
        TwelveDataSource(KEY, FakeSession(FakeResponse(payload, 401)), pace=False).daily_bars("AAPL", 1)
    assert KEY not in str(exc.value)


def test_network_error_never_contains_the_key():
    failure = requests.ConnectionError(f"https://x/?apikey={KEY}")
    with pytest.raises(SourceError) as exc:
        TwelveDataSource(KEY, FakeSession(failure, failure, failure), pace=False).daily_bars("AAPL", 1)
    assert KEY not in str(exc.value)


def test_unexpected_shape_is_a_source_error():
    with pytest.raises(SourceError):
        TwelveDataSource(KEY, FakeSession(FakeResponse({"values": [{}]})), pace=False).daily_bars("AAPL", 1)


def kline(day_ms):
    return [day_ms, "1", "2", "0.5", "1.5", "10"]


def test_binance_parses_and_pages_oldest_first():
    day = 86_400_000
    first_page = [kline(i * day) for i in range(1000)]
    session = FakeSession(FakeResponse(first_page), FakeResponse([kline(1000 * day)]))
    bars = BinanceSource(session=session, pace=False).daily_bars("EOSUSDT", 5000)
    assert len(bars) == 1001
    assert session.calls[0]["startTime"] == 0
    assert session.calls[1]["startTime"] == 1000 * day
    assert bars[0].date == date(1970, 1, 1)


def test_binance_recent_needs_one_request():
    session = FakeSession(FakeResponse([kline(0)]))
    assert len(BinanceSource(session=session, pace=False).daily_bars("EOSUSDT", 10)) == 1
    assert "startTime" not in session.calls[0]


def test_alphavantage_silver_is_close_only():
    payload = {"data": [{"date": "2026-11-03", "price": "30.5"}, {"date": "2026-11-02", "price": "30"}]}
    session = FakeSession(FakeResponse(payload))
    bars = AlphaVantageSource(KEY, session, pace=False).daily_bars("SILVER", 10)
    assert [b.close for b in bars] == [Decimal("30"), Decimal("30.5")]
    assert bars[0].basis == "close" and bars[0].open is None
    assert session.calls[0]["function"] == "GOLD_SILVER_HISTORY"


def test_alphavantage_oil_skips_missing_days():
    payload = {"data": [{"date": "2026-11-03", "value": "99.6"}, {"date": "2026-11-02", "value": "."}]}
    session = FakeSession(FakeResponse(payload))
    bars = AlphaVantageSource(KEY, session, pace=False).daily_bars("WTI", 10)
    assert len(bars) == 1
    assert session.calls[0]["function"] == "WTI"


def test_alphavantage_share():
    row = {"1. open": "57", "2. high": "58", "3. low": "56", "4. close": "57.8", "5. volume": "1000"}
    session = FakeSession(FakeResponse({"Time Series (Daily)": {"2026-11-03": row}}))
    bars = AlphaVantageSource(KEY, session, pace=False).daily_bars("BMW.DEX", 100)
    assert bars[0].close == Decimal("57.8") and bars[0].basis == "full"
    assert session.calls[0]["function"] == "TIME_SERIES_DAILY"


def test_alphavantage_limit_message_is_cleaned():
    payload = {"Information": f"We have detected your API key as {KEY} and the limit is 25."}
    with pytest.raises(SourceError) as exc:
        session = FakeSession(FakeResponse(payload), FakeResponse(payload))
        AlphaVantageSource(KEY, session, pace=False).daily_bars("WTI", 1)
    assert KEY not in str(exc.value)


def test_fred_returns_oldest_first_and_skips_gaps():
    payload = {
        "observations": [
            {"date": "2026-11-03", "value": "4.47"},
            {"date": "2026-11-02", "value": "."},
            {"date": "2026-10-30", "value": "4.708"},
        ]
    }
    bars = FredSource(KEY, FakeSession(FakeResponse(payload)), pace=False).daily_bars("DHOILNYH", 10)
    assert [b.date.day for b in bars] == [30, 3]
    assert bars[0].basis == "close"


def test_fred_error_message():
    payload = {"error_code": 400, "error_message": f"Bad key {KEY}"}
    with pytest.raises(SourceError) as exc:
        FredSource(KEY, FakeSession(FakeResponse(payload, 400)), pace=False).daily_bars("DHOILNYH", 10)
    assert KEY not in str(exc.value)


def test_kraken_parses_rows():
    row = [1793836800, "1.4", "1.5", "1.3", "1.45", "1.42", "1000.5", 3313]
    payload = {"error": [], "result": {"TONUSD": [row], "last": 1793836800}}
    bars = KrakenSource(session=FakeSession(FakeResponse(payload)), pace=False).daily_bars("TONUSD", 10)
    assert bars[0].close == Decimal("1.45") and bars[0].volume == 1000.5


def test_kraken_error():
    payload = {"error": ["EQuery:Unknown asset pair"]}
    with pytest.raises(SourceError):
        KrakenSource(session=FakeSession(FakeResponse(payload)), pace=False).daily_bars("NOPE", 10)


def test_finnhub_quote():
    payload = {"c": 349.51, "dp": 5.3, "t": 1793826000}
    quote = FinnhubSource(KEY, FakeSession(FakeResponse(payload)), pace=False).quote("AAPL")
    assert quote == {"price": 349.51, "change_pct": 5.3, "time": 1793826000}


def test_finnhub_unknown_symbol():
    with pytest.raises(SourceError):
        FinnhubSource(KEY, FakeSession(FakeResponse({"c": 0})), pace=False).quote("NOPE")
