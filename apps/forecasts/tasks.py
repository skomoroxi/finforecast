"""Forecast jobs (TECHNICAL-TASK §13). Heavy libraries load inside the tasks, so the web process stays small."""

from celery import shared_task

from apps.market.models import Asset
from apps.market.services import run_assets


@shared_task
def run_due_forecasts() -> None:
    from . import services

    run_assets("forecast", services.due_assets(), action=services.forecast_asset)


@shared_task
def forecast_codes(codes: list[str]) -> None:
    from . import services

    assets = Asset.objects.filter(code__in=codes, series_of=None).select_related("asset_class")
    run_assets("forecast:manual", assets, action=services.forecast_asset)


@shared_task
def update_accuracy() -> None:
    from . import accuracy

    assets = Asset.objects.filter(enabled=True, series_of=None, forecast_runs__isnull=False)
    run_assets("accuracy", assets.distinct().select_related("asset_class"), action=accuracy.update_asset)
