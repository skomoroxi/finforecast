from datetime import date, timedelta
from decimal import Decimal as D

import pytest
from django.core.management import call_command
from django.db import connection

from apps.market import catalog, ratelimit, services
from apps.market.models import AdrConversion, Asset, FetchResult, PriceBar
from apps.market.sources import Bar, SourceError


def bar(day, close="100", **kw):
    return Bar(date=day, close=D(close), **kw)


def test_clean_drops_today_weekends_and_bad_prices():
    today = date(2026, 11, 5)  # Thursday
    bars = [
        bar(date(2026, 10, 31)),  # Saturday
        bar(date(2026, 11, 2), "0"),
        bar(date(2026, 11, 3)),
        bar(today),
    ]
    assert [b.date for b in services.clean_bars(bars, "nyse", today)] == [date(2026, 11, 3)]
    assert len(services.clean_bars(bars, "crypto", today)) == 2


def test_jump_check():
    bars = [bar(date(2026, 11, 3), "105"), bar(date(2026, 11, 4), "160")]
    with pytest.raises(services.PriceJump):
        services.check_jumps(D("100"), bars, 0.3)
    services.check_jumps(D("100"), bars[:1], 0.3)
    services.check_jumps(None, bars[:1], 0.3)


def test_average_is_typical_price_or_close():
    assert services.average(bar(date(2026, 11, 3), "3", high=D("4"), low=D("2"))) == D("3")
    assert services.average(bar(date(2026, 11, 3), "5", basis="close")) == D("5")


def test_budget_is_enforced(settings, monkeypatch):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "budget"}}
    monkeypatch.setitem(ratelimit.LIMITS, "alphavantage", ratelimit.Limit(interval=0, per_day=2))
    ratelimit.acquire("alphavantage")
    ratelimit.acquire("alphavantage")
    with pytest.raises(ratelimit.BudgetExceeded):
        ratelimit.acquire("alphavantage")


def test_catalog_matches_the_approved_list():
    rows = catalog.asset_rows()
    assert len({r["code"] for r in rows}) == len(rows)
    pages = [r for r in rows if "series_of" not in r]
    by_class = {}
    for row in pages:
        by_class[row["asset_class"]] = by_class.get(row["asset_class"], 0) + 1
    assert by_class == {"crypto": 33, "stock": 40, "etf_index": 3, "fx": 6, "metal": 2, "energy": 2}
    assert len(pages) == 86


@pytest.fixture
def seeded(db):
    call_command("seed_assets", verbosity=0)


class FakeSource:
    def __init__(self, bars):
        self.bars = bars

    def daily_bars(self, symbol, count):
        if isinstance(self.bars, Exception):
            raise self.bars
        return self.bars


def weekdays(count, end=None):
    day = end or date(2026, 11, 4)
    out = []
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day)
        day -= timedelta(days=1)
    return sorted(out)


def test_seed_is_repeatable_and_keeps_admin_edits(seeded):
    assert Asset.objects.count() == len(catalog.asset_rows())
    assert AdrConversion.objects.count() == 14
    Asset.objects.filter(code="BTC").update(name="Edited")
    call_command("seed_assets", verbosity=0)
    assert Asset.objects.get(code="BTC").name == "Edited"
    assert Asset.objects.get(code="BRENT").series_of.code == "WTI"
    assert Asset.objects.get(code="XAG").proxy.code == "SLV"


def test_price_table_is_a_hypertable(seeded):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM timescaledb_information.hypertables WHERE hypertable_name = %s", ["market_pricebar"]
        )
        assert cursor.fetchone()[0] == 1


def test_update_stores_and_revises_bars(seeded, monkeypatch):
    asset = Asset.objects.get(code="AAPL")
    day = weekdays(1)[0]
    monkeypatch.setattr(services, "get_source", lambda name: FakeSource([bar(day, "10", high=D("12"), low=D("8"))]))
    assert services.update_asset(asset)[0] == 1
    assert PriceBar.objects.get(asset=asset, date=day).avg == D("10")

    monkeypatch.setattr(services, "get_source", lambda name: FakeSource([bar(day, "11", high=D("12"), low=D("10"))]))
    services.update_asset(asset)
    assert PriceBar.objects.filter(asset=asset).count() == 1
    assert PriceBar.objects.get(asset=asset, date=day).close == D("11")


def test_price_jump_is_rejected_and_old_data_stays(seeded, monkeypatch):
    asset = Asset.objects.get(code="AAPL")
    first, second = weekdays(2)
    services.save_bars(asset, [bar(first, "10")], "twelvedata")
    monkeypatch.setattr(services, "get_source", lambda name: FakeSource([bar(second, "100")]))
    with pytest.raises(services.PriceJump):
        services.update_asset(asset)
    assert PriceBar.objects.filter(asset=asset).count() == 1


def test_fallback_source_is_used(seeded, monkeypatch):
    asset = Asset.objects.get(code="BTC")
    day = weekdays(1)[0]

    def source(name):
        return FakeSource(SourceError("down")) if name == "twelvedata" else FakeSource([bar(day)])

    monkeypatch.setattr(services, "get_source", source)
    assert services.update_asset(asset)[2] == "binance"


def test_sonic_history_is_joined_from_fantom(seeded, monkeypatch):
    asset = Asset.objects.get(code="S")
    old, new = weekdays(2)

    def source(name):
        return FakeSource([bar(new)]) if name == "twelvedata" else FakeSource([bar(old, "1"), bar(new, "999")])

    monkeypatch.setattr(services, "get_source", source)
    services.update_asset(asset, full=True)
    closes = list(PriceBar.objects.filter(asset=asset).order_by("date").values_list("close", flat=True))
    assert closes == [D("1"), D("100")]


def test_silver_range_comes_from_slv(seeded, monkeypatch):
    silver = Asset.objects.get(code="XAG")
    day = weekdays(1)[0]
    slv = Bar(date=day, open=D("27"), high=D("28"), low=D("26"), close=D("27"))
    services.save_bars(Asset.objects.get(code="SLV"), [slv], "twelvedata")
    monkeypatch.setattr(services, "get_source", lambda name: FakeSource([bar(day, "54", basis="close")]))
    services.update_asset(silver)
    stored = PriceBar.objects.get(asset=silver, date=day)
    assert stored.basis == "proxy"
    assert (stored.high, stored.low) == (D("56"), D("52"))


def test_failed_asset_does_not_stop_the_run(seeded, monkeypatch):
    day = weekdays(1)[0]

    def source(name):
        return FakeSource(SourceError("boom")) if name == "fred" else FakeSource([bar(day, basis="close")])

    monkeypatch.setattr(services, "get_source", source)
    run = services.run_assets(
        "test", Asset.objects.filter(asset_class__code="energy").select_related("asset_class", "proxy")
    )
    assert (run.ok_count, run.error_count) == (2, 1)
    assert FetchResult.objects.get(run=run, asset__code="HEATOIL").message.startswith("SourceError: boom")


def adr_setup(days=30):
    """BMW-like share: ratio 3, EUR/USD 1.2, ADR $20, so XETRA should be 50 euros."""
    conv = AdrConversion.objects.select_related("asset", "adr_asset").get(asset__code="BMW")
    dates = weekdays(days)
    services.save_bars(Asset.objects.get(code="EURUSD"), [bar(d, "1.2") for d in dates], "twelvedata")
    adr = [Bar(date=d, close=D("20"), open=D("19"), high=D("21"), low=D("18")) for d in dates]
    services.save_bars(conv.adr_asset, adr, "twelvedata")
    return conv, dates


def test_ratio_is_the_median_and_estimates_history(seeded, monkeypatch):
    conv, dates = adr_setup()
    xetra = [bar(d, "50") for d in dates[-25:]]
    xetra[-1] = bar(dates[-1], "60")  # an outlier does not move a median
    monkeypatch.setattr(services, "get_source", lambda name: FakeSource(xetra))
    services.recalc_ratio(conv)
    assert conv.ratio_auto == D("3")
    assert conv.status == AdrConversion.Status.OK

    estimated = PriceBar.objects.get(asset=conv.asset, date=dates[0])
    assert estimated.close == D("50") and estimated.basis == "estimate" and estimated.source == "adr"
    assert estimated.high == D("52.5")
    real = PriceBar.objects.get(asset=conv.asset, date=dates[-1])
    assert real.close == D("60") and real.source == "alphavantage"


def test_manual_ratio_wins(seeded):
    conv, dates = adr_setup()
    conv.ratio_auto = D("3")
    conv.ratio_manual = D("6")
    conv.save()
    services.rebuild_adr(conv)
    assert PriceBar.objects.get(asset=conv.asset, date=dates[0]).close == D("100")


def test_ratio_jump_pauses_the_share(seeded, monkeypatch):
    conv, dates = adr_setup()
    conv.ratio_auto = D("1.5")
    conv.status = AdrConversion.Status.OK
    conv.save()
    monkeypatch.setattr(services, "get_source", lambda name: FakeSource([bar(d, "50") for d in dates]))
    with pytest.raises(services.RatioPaused):
        services.recalc_ratio(conv)
    conv.refresh_from_db()
    assert conv.status == AdrConversion.Status.PAUSED
    assert conv.ratio_auto == D("1.5") and conv.ratio_candidate == D("3")
    with pytest.raises(services.RatioPaused):
        services.update_asset(conv.asset)


def test_too_little_overlap_is_an_error(seeded, monkeypatch):
    conv, dates = adr_setup(days=5)
    monkeypatch.setattr(services, "get_source", lambda name: FakeSource([bar(d, "50") for d in dates]))
    with pytest.raises(SourceError):
        services.recalc_ratio(conv)
