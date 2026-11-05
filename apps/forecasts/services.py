"""Forecast one asset from its stored prices and keep everything (TECHNICAL-TASK §6.3, §13)."""

from datetime import date, timedelta

import pandas as pd
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from apps.market.models import Asset, PriceBar

from .engine import backtest, build
from .models import ForecastAccuracy, ForecastPoint, ForecastRun, TechnicalSnapshot
from .ta import build as ta_build

MIN_BARS = 60
SMALL_SITE = "small-site"
MODEL_MAX_AGE_DAYS = 7  # the ARIMA order search is 32 fits; once a week is enough
BACKTEST_MAX_AGE_DAYS = 7


class NotEnoughData(RuntimeError):
    pass


def load_frame(asset: Asset) -> pd.DataFrame:
    rows = PriceBar.objects.filter(asset=asset).order_by("date").values_list("date", "open", "high", "low", "close")
    frame = pd.DataFrame(list(rows), columns=["date", "open", "high", "low", "close"])
    frame.index = pd.DatetimeIndex(frame.pop("date"))
    return frame.astype(float)


def drift_cap(asset: Asset) -> float:
    if asset.max_annual_drift is not None:
        return asset.max_annual_drift
    return asset.asset_class.max_annual_drift


def recent_model(asset: Asset, today: date):
    """The ARIMA order picked in the last week, if any, so a daily run skips the search."""
    run = ForecastRun.objects.filter(asset=asset).order_by("-run_date").first()
    params = ((run.methods if run else {}).get("arima") or {}).get("params") or {}
    if "selected_on" not in params or "order" not in params:
        return None
    if today - date.fromisoformat(params["selected_on"]) >= timedelta(days=MODEL_MAX_AGE_DAYS):
        return None
    return tuple(params["order"]), ("t" if params["model_drift"] else "n"), params["selected_on"]


def ohlc_basis(asset: Asset, frame: pd.DataFrame) -> str:
    if not ta_build.has_ranges(frame):
        return "close"
    basis = PriceBar.objects.filter(asset=asset).order_by("-date").values_list("basis", flat=True)[:30]
    if "estimate" in basis:
        return "estimate"
    return "proxy" if "proxy" in basis else "full"


def save_backtest(asset: Asset, close: pd.Series, info: dict, today: date) -> None:
    calendar = asset.asset_class.calendar
    arima_params = info["arima"]["params"] if info["arima"]["status"] == "ok" else None
    model = ((0, 1, 1), "n")
    if arima_params:
        model = (tuple(arima_params["order"]), "t" if arima_params["model_drift"] else "n")
    cap = build.daily_drift_cap(drift_cap(asset), calendar)
    rows = backtest.walk_forward(close, calendar, build.windows(calendar), cap, model)
    ForecastAccuracy.objects.filter(asset=asset, basis=ForecastAccuracy.Basis.BACKTEST).delete()
    ForecastAccuracy.objects.bulk_create(
        ForecastAccuracy(asset=asset, basis=ForecastAccuracy.Basis.BACKTEST, computed_on=today, **row) for row in rows
    )


def backtest_is_due(asset: Asset, today: date) -> bool:
    latest = ForecastAccuracy.objects.filter(asset=asset, basis=ForecastAccuracy.Basis.BACKTEST).first()
    return latest is None or today - latest.computed_on >= timedelta(days=BACKTEST_MAX_AGE_DAYS)


def forecast_asset(asset: Asset) -> tuple[int, date, str]:
    """Forecast, technicals and, when due, the backtest. Returns (points stored, last close date, version)."""
    frame = load_frame(asset)
    if len(frame) < MIN_BARS:
        raise NotEnoughData(f"only {len(frame)} days of prices")

    today = timezone.now().date()
    close = frame["close"]
    calendar = asset.asset_class.calendar
    points, info = build.build(close, calendar, drift_cap(asset), today, recent_model(asset, today))
    if all(m["status"] != "ok" for m in info.values()):
        raise RuntimeError("; ".join(f"{n}: {m['error']}" for n, m in info.items())[:250])

    technicals = ta_build.build(frame)
    data_date = frame.index[-1].date()
    with transaction.atomic():
        run, _ = ForecastRun.objects.update_or_create(
            asset=asset,
            run_date=today,
            defaults={
                "data_date": data_date,
                "last_close": float(close.iloc[-1]),
                "model_version": build.MODEL_VERSION,
                "methods": info,
            },
        )
        ForecastPoint.objects.filter(run=run, run_date=today).delete()
        ForecastPoint.objects.bulk_create(
            [
                ForecastPoint(
                    run_date=today,
                    run=run,
                    asset=asset,
                    method=p.method,
                    horizon=p.horizon,
                    target=p.target,
                    value=p.value,
                    p10=p.p10,
                    p90=p.p90,
                )
                for p in points
            ],
            batch_size=500,
        )
        TechnicalSnapshot.objects.update_or_create(
            asset=asset,
            defaults={"run_date": today, "ohlc_basis": ohlc_basis(asset, frame), "timeframes": technicals},
        )
    if backtest_is_due(asset, today):
        save_backtest(asset, close, info, today)
    return len(points), data_date, build.MODEL_VERSION


def due_assets():
    """Pages with a newer close than their latest forecast saw: weekends and holidays cost nothing."""
    last_bar = Subquery(
        PriceBar.objects.filter(asset=OuterRef("pk")).order_by("-date").values("date")[:1],
    )
    last_seen = Subquery(
        ForecastRun.objects.filter(asset=OuterRef("pk"))
        .exclude(model_version=SMALL_SITE)  # imported history; the asset still needs its own forecast
        .order_by("-run_date")
        .values("data_date")[:1],
    )
    pages = Asset.objects.filter(enabled=True, series_of=None).select_related("asset_class")
    pages = pages.annotate(last_bar=last_bar, last_seen=last_seen).exclude(last_bar=None)
    return [a for a in pages if a.last_seen is None or a.last_bar > a.last_seen]
