"""The ported engine. No database: these run anywhere."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from apps.forecasts.engine import backtest, build, montecarlo, reversion
from apps.forecasts.engine.common import MethodForecast, future_dates, sanity_check
from apps.forecasts.ta import build as ta_build
from apps.forecasts.ta import indicators as ind
from apps.forecasts.ta import rules


def prices(n=700, seed=7, drift=0.0003, vol=0.015, start=50.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = start * np.exp(np.cumsum(drift + vol * rng.standard_normal(n)))
    open_ = close * (1 + 0.003 * rng.standard_normal(n))
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) * 1.006,
            "low": np.minimum(open_, close) * 0.994,
            "close": close,
        },
        index=pd.bdate_range("2023-01-02", periods=n),
    )


@pytest.fixture(scope="module")
def built():
    close = prices()["close"]
    run_date = close.index[-1].date()
    points, info = build.build(close, "fx", 0.25, run_date, model=((0, 1, 1), "n", "2026-01-01"))
    return close, run_date, points, info


def test_future_dates_skip_weekends_on_weekday_calendars():
    d = future_dates(date(2026, 10, 28), date(2026, 11, 6), "fx")
    assert all(x.weekday() < 5 for x in d) and len(d) == 7
    assert len(future_dates(date(2026, 10, 28), date(2026, 11, 6), "crypto")) == 9


def test_all_methods_produce_daily_monthly_and_yearly_points(built):
    _, _, points, info = built
    assert all(m["status"] == "ok" for m in info.values())
    kinds = {(p.method, p.horizon) for p in points}
    for method in ("arima", "reversion", "montecarlo", "consensus"):
        assert (method, "daily") in kinds and (method, "monthly") in kinds
    assert ("arima", "yearly") not in kinds  # ARIMA adds nothing beyond 2030
    assert ("consensus", "yearly") in kinds
    assert sum(p.horizon == "yearly" for p in points) == 15
    assert all(p.p10 <= p.value <= p.p90 for p in points if p.method == "consensus")


def test_monthly_runs_to_december_2030(built):
    _, _, points, _ = built
    assert max(p.target for p in points if p.horizon == "monthly") == date(2030, 12, 1)


def test_growth_cap_holds_on_a_runaway_series():
    close = prices(n=500, drift=0.01, vol=0.01)["close"]
    run_date = close.index[-1].date()
    points, _ = build.build(close, "fx", 0.25, run_date, model=((0, 1, 1), "t", "2026-01-01"))
    yearly = [p for p in points if p.method == "montecarlo" and p.target == date(2035, 1, 1)]
    years = (date(2035, 7, 1) - run_date).days / 365
    assert yearly[0].value / float(close.iloc[-1]) < 1.25**years * 1.05


def test_tiny_prices_survive_rounding():
    assert build.sig(0.00000473219) == pytest.approx(0.00000473219, rel=1e-6)
    close = prices(n=400, start=0.000005)["close"]
    points, _ = build.build(close, "crypto", 0.25, close.index[-1].date(), model=((0, 1, 1), "n", "2026-01-01"))
    assert all(p.value > 0 for p in points)


def test_reversion_moves_deviation_back_to_trend():
    t = np.arange(2000)
    y = np.log(40) + 0.0002 * t + 0.3 * np.exp(-((t - 1999) ** 2) / 1e5)  # ends 35% above trend
    p = reversion.fit(y)
    mid, low, high = reversion.predict_log(p, 3000)
    trend_end = p["a"] + p["b"] * (p["n"] - 1 + 3000)
    assert abs(mid[-1] - trend_end) < abs(mid[0] - (p["a"] + p["b"] * p["n"]))
    assert np.all(low < mid) and np.all(mid < high)


def test_montecarlo_is_reproducible_and_ordered():
    close = prices()["close"]
    dates = future_dates(close.index[-1].date(), date(2027, 6, 30), "fx")
    a = montecarlo.forecast(close, dates, 300, 200, seed=42, paths=2000)
    b = montecarlo.forecast(close, dates, 300, 200, seed=42, paths=2000)
    assert np.array_equal(a.mid, b.mid)
    assert np.all(a.low <= a.mid) and np.all(a.mid <= a.high)


def test_sanity_check_rejects_explosive_path():
    dates = pd.bdate_range("2026-11-02", periods=300)
    mid = np.linspace(50, 900, 300)
    fc = sanity_check(MethodForecast("x", dates, mid, mid * 0.9, mid * 1.1), 50, date(2026, 10, 30))
    assert fc.status == "failed"


def test_one_failing_method_leaves_the_others(monkeypatch):
    monkeypatch.setattr(build.arima, "forecast", lambda *a, **k: 1 / 0)
    close = prices(n=300)["close"]
    points, info = build.build(close, "fx", 0.25, close.index[-1].date())
    assert info["arima"]["status"] == "failed"
    assert info["reversion"]["status"] == "ok"
    assert not any(p.method == "arima" for p in points)
    assert any(p.method == "consensus" for p in points)


def test_jsonable_has_no_numpy_or_nan():
    out = build.jsonable({"a": np.float64(1.5), "b": float("nan"), "c": [np.int64(2)]})
    assert out == {"a": 1.5, "b": None, "c": [2]}


def test_walk_forward_reports_every_method_and_horizon():
    close = prices(n=500)["close"]
    w = build.windows("fx")
    rows = backtest.walk_forward(close, "fx", w, 0.001, ((0, 1, 1), "n"), origins=4, step=5)
    assert len(rows) == 12
    assert {r["horizon"] for r in rows} == {"1d", "7d", "30d"}
    assert all(r["samples"] == 4 and r["mape"] > 0 for r in rows)


def test_young_asset_still_gets_a_backtest():
    close = prices(n=320)["close"]
    rows = backtest.walk_forward(close, "fx", build.windows("fx"), 0.001, ((0, 1, 1), "n"), origins=2, step=5)
    assert rows


def test_too_short_for_a_backtest_returns_nothing():
    close = prices(n=100)["close"]
    assert backtest.walk_forward(close, "fx", build.windows("fx"), 0.001, ((0, 1, 1), "n")) == []


def test_technicals_cover_all_timeframes():
    out = ta_build.build(prices())
    assert set(out) == {"daily", "weekly", "monthly"}
    daily = out["daily"]
    assert len(daily["oscillators"]) == 12
    assert len(daily["moving_averages"]) == 6
    assert set(daily["pivots"]) == {"classic", "fibonacci", "camarilla", "woodie", "demark"}
    assert daily["summary"]["overall"]["verdict"] in ("strong_sell", "sell", "neutral", "buy", "strong_buy")
    assert sum(daily["summary"]["oscillators"][k] for k in ("buy", "sell", "neutral")) == 11  # ATR has no direction


def test_close_only_assets_skip_what_needs_a_range():
    df = prices()
    df[["open", "high", "low"]] = np.nan
    daily = ta_build.build(df)["daily"]
    assert [o["name"] for o in daily["oscillators"]] == ["rsi_14", "stochrsi_14", "macd_12_26", "roc_12"]
    assert daily["pivots"] == {}
    assert daily["moving_averages"][0]["simple"]["value"] is not None


def test_technicals_of_a_tiny_price_are_not_rounded_away():
    daily = ta_build.build(prices(start=0.000005))["daily"]
    assert daily["moving_averages"][0]["simple"]["value"] > 0
    assert daily["pivots"]["classic"]["p"] > 0


def test_rsi_extremes():
    up = pd.DataFrame({"close": np.arange(1.0, 60.0)})
    assert ind.rsi(up) == pytest.approx(100)
    assert rules.zone(75, 50, 30, 70) == rules.OVERBOUGHT


def test_verdict_bands():
    assert rules.verdict(10, 0, 0) == "strong_buy"
    assert rules.verdict(0, 10, 0) == "strong_sell"
    assert rules.verdict(5, 5, 0) == "neutral"
