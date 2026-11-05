from celery import shared_task

from apps.market.models import Asset
from apps.market.services import run_assets


@shared_task
def create_drafts(codes: list[str], language: str = "en") -> None:
    from . import drafts

    assets = Asset.objects.filter(code__in=codes, series_of=None).select_related("asset_class")
    run_assets("ai-draft", assets, action=lambda asset: drafts.draft_asset(asset, language))
