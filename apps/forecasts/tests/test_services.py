from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from apps.forecasts import accuracy, services
from apps.forecasts.models import ForecastAccuracy, ForecastPoint, ForecastRun, TechnicalSnapshot
from apps.market.models import Asset, PriceBar


def add_bars(asset, n=300, close_only=False, end=None):
    end = end or timezone.now().date() - timedelta(days=1)
    rng = np.random.default_rng(3)
    closes = 100 * np.exp(np.cumsum(0.0002 + 0.01 * rng.standard_normal(n)))
    freq = "D" if asset.asset_class.calendar == "crypto" else "B"
    days = pd.date_range(end=end, periods=n, freq=freq)
    PriceBar.objects.bulk_create(
        PriceBar(
            asset=asset,
            date=d.date(),
            open=None if close_only else Decimal(str(round(c, 4))),
            high=None if close_only else Decimal(str(round(c * 1.01, 4))),
            low=None if close_only else Decimal(str(round(c * 0.99, 4))),
            close=Decimal(str(round(c, 4))),
            avg=Decimal(str(round(c, 4))),
            source="twelvedata",
            basis="close" if close_only else "full",
        )
        for d, c in zip(days, closes, strict=True)
    )
    return [d.date() for d in days]


@pytest.fixture
def seeded(db):
    call_command("seed_assets", verbosity=0)


@pytest.fixture
def quick(monkeypatch):
    """No order search: most tests are not about it."""
    monkeypatch.setattr(services, "recent_model", lambda asset, today: ((0, 1, 1), "n", today.isoformat()))


def test_point_table_is_a_compressed_hypertable(seeded):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT compression_enabled FROM timescaledb_information.hypertables WHERE hypertable_name = %s",
            ["forecasts_forecastpoint"],
        )
        assert cursor.fetchone() == (True,)


def test_forecast_stores_run_points_and_technicals(seeded, quick):
    asset = Asset.objects.get(code="AAPL")
    days = add_bars(asset)
    written, last, _ = services.forecast_asset(asset)
    run = ForecastRun.objects.get(asset=asset)
    assert last == days[-1] == run.data_date
    assert ForecastPoint.objects.filter(run=run).count() == written > 200
    assert ForecastPoint.objects.filter(run=run, method="consensus", horizon="yearly").count() == 5
    snapshot = TechnicalSnapshot.objects.get(asset=asset)
    assert snapshot.ohlc_basis == "full"
    assert "daily" in snapshot.timeframes
    assert ForecastAccuracy.objects.filter(asset=asset, basis="backtest").exists()


def test_running_twice_a_day_replaces_the_run(seeded, quick):
    asset = Asset.objects.get(code="AAPL")
    add_bars(asset)
    first, *_ = services.forecast_asset(asset)
    services.forecast_asset(asset)
    assert ForecastRun.objects.filter(asset=asset).count() == 1
    assert ForecastPoint.objects.filter(asset=asset).count() == first


def test_close_only_asset(seeded, quick):
    asset = Asset.objects.get(code="WTI")
    add_bars(asset, close_only=True)
    services.forecast_asset(asset)
    snapshot = TechnicalSnapshot.objects.get(asset=asset)
    assert snapshot.ohlc_basis == "close"
    assert len(snapshot.timeframes["daily"]["oscillators"]) == 4


def test_too_little_history_is_an_error(seeded):
    asset = Asset.objects.get(code="AAPL")
    add_bars(asset, n=20)
    with pytest.raises(services.NotEnoughData):
        services.forecast_asset(asset)


def test_arima_order_is_reused_within_a_week_then_searched_again(seeded):
    asset = Asset.objects.get(code="AAPL")
    today = timezone.now().date()
    params = {"order": [1, 1, 1], "model_drift": True, "selected_on": (today - timedelta(days=3)).isoformat()}
    ForecastRun.objects.create(
        asset=asset,
        run_date=today,
        data_date=today,
        last_close=1,
        model_version="1",
        methods={"arima": {"params": params}},
    )
    assert services.recent_model(asset, today) == ((1, 1, 1), "t", params["selected_on"])
    assert services.recent_model(asset, today + timedelta(days=7)) is None


def test_only_assets_with_a_new_close_are_due(seeded, quick):
    apple, msft = Asset.objects.get(code="AAPL"), Asset.objects.get(code="MSFT")
    add_bars(apple)
    add_bars(msft)
    assert {a.code for a in services.due_assets()} == {"AAPL", "MSFT"}
    services.forecast_asset(apple)
    assert {a.code for a in services.due_assets()} == {"MSFT"}


def test_imported_runs_do_not_count_as_forecast_done(seeded):
    asset = Asset.objects.get(code="AAPL")
    days = add_bars(asset)
    ForecastRun.objects.create(
        asset=asset, run_date=days[-1], data_date=days[-1], last_close=1, model_version=services.SMALL_SITE
    )
    assert [a.code for a in services.due_assets()] == ["AAPL"]


def test_supporting_series_get_no_forecast(seeded):
    add_bars(Asset.objects.get(code="BRENT"))
    assert services.due_assets() == []


def make_run(asset, run_date, last_close, rows, horizon="daily", method="consensus"):
    run, _ = ForecastRun.objects.get_or_create(
        asset=asset,
        run_date=run_date,
        defaults={"data_date": run_date, "last_close": last_close, "model_version": "t"},
    )
    ForecastPoint.objects.bulk_create(
        ForecastPoint(
            run_date=run_date, run=run, asset=asset, method=method, horizon=horizon, target=t, value=v, p10=lo, p90=hi
        )
        for t, v, lo, hi in rows
    )
    return run


def test_metrics():
    rows = pd.DataFrame(
        {
            "value": [110.0, 90.0],
            "actual": [100.0, 100.0],
            "base": [100.0, 95.0],
            "p10": [105.0, 80.0],
            "p90": [120.0, 120.0],
        }
    )
    m = accuracy.metrics(rows)
    assert m["mape"] == pytest.approx(10)
    assert m["mae"] == pytest.approx(10)
    assert m["bias_pct"] == pytest.approx(0)
    assert m["direction_pct"] == pytest.approx(0)  # flat counted as no rise; the second call was wrong
    assert m["in_range_pct"] == pytest.approx(50)
    assert m["samples"] == 2


def test_live_accuracy_matches_forecasts_with_real_prices(seeded):
    asset = Asset.objects.get(code="BTC")
    days = add_bars(asset, n=20)
    run_date = days[0]
    base = float(PriceBar.objects.get(asset=asset, date=days[0]).close)
    actual = float(PriceBar.objects.get(asset=asset, date=days[1]).close)
    rows = [(d, actual * 1.1, actual, actual * 1.2) for d in days[1:12]]
    make_run(asset, run_date, base, rows)

    written, *_ = accuracy.update_asset(asset)
    assert written >= 2
    row = ForecastAccuracy.objects.get(asset=asset, basis="live", horizon="1d", window_days=30)
    assert row.mape == pytest.approx(10)
    assert row.samples == 1
    assert row.in_range_pct == 100
    assert ForecastAccuracy.objects.filter(asset=asset, basis="live", horizon="7d", window_days=365).exists()
    assert not ForecastAccuracy.objects.filter(asset=asset, basis="live", horizon="30d").exists()


def test_unmatured_forecasts_count_for_nothing(seeded):
    asset = Asset.objects.get(code="BTC")
    today = timezone.now().date()
    add_bars(asset, n=5)
    make_run(asset, today, 100, [(today + timedelta(days=1), 110, None, None)])
    assert accuracy.update_asset(asset)[0] == 0


def test_month_accuracy_uses_the_next_finished_month(seeded):
    asset = Asset.objects.get(code="BTC")
    today = timezone.now().date()
    first_of_this = today.replace(day=1)
    previous = (first_of_this - timedelta(days=1)).replace(day=1)
    run_date = previous - timedelta(days=1)
    add_bars(asset, n=120)
    average = np.mean(
        [
            float(c)
            for c in PriceBar.objects.filter(asset=asset, date__gte=previous, date__lt=first_of_this).values_list(
                "close", flat=True
            )
        ]
    )
    make_run(asset, run_date, 100, [(previous, average * 1.05, None, None)], horizon="monthly")
    make_run(asset, run_date, 100, [(first_of_this, 1.0, None, None)], horizon="monthly", method="arima")
    accuracy.update_asset(asset)
    row = ForecastAccuracy.objects.get(asset=asset, basis="live", horizon="month", window_days=365)
    assert row.mape == pytest.approx(5)
    assert row.method == "consensus"


def accuracy_row(asset, basis, samples, horizon="1d"):
    return ForecastAccuracy.objects.create(
        asset=asset,
        method="consensus",
        horizon=horizon,
        window_days=90 if basis == "live" else 0,
        basis=basis,
        mape=1,
        mae=1,
        samples=samples,
        computed_on=date(2026, 11, 5),
    )


def test_display_prefers_live_once_there_are_30_samples(seeded):
    asset = Asset.objects.get(code="BTC")
    accuracy_row(asset, "backtest", 50, "1d")
    accuracy_row(asset, "backtest", 50, "7d")
    accuracy_row(asset, "live", 30, "1d")
    accuracy_row(asset, "live", 29, "7d")
    shown = {(r.horizon, r.basis) for r in accuracy.for_display(asset)}
    assert shown == {("1d", "live"), ("7d", "backtest")}


def test_small_site_import(seeded):
    call_command("import_smallsite", verbosity=0)
    run = ForecastRun.objects.filter(asset__code="XAG", model_version="small-site").first()
    assert run is not None
    points = ForecastPoint.objects.filter(run=run)
    assert {p.method for p in points} == {"arima", "reversion", "montecarlo", "consensus"}
    assert points.filter(method="consensus", p10__isnull=False).exists()
    count = ForecastRun.objects.count()
    call_command("import_smallsite", verbosity=0)
    assert ForecastRun.objects.count() == count
