"""The admin home page: what needs attention today."""

from datetime import timedelta

from django.db.models import Max, Q
from django.utils import timezone

from apps.content.models import Draft
from apps.market.models import AdrConversion, Asset, FetchResult, FetchRun

STALE_AFTER_DAYS = 5
RECENT_RUNS = 12


def callback(request, context):
    today = timezone.now().date()
    pages = Asset.objects.filter(enabled=True, series_of=None)
    cutoff = today - timedelta(days=STALE_AFTER_DAYS)
    stale = pages.annotate(last=Max("bars__date")).filter(Q(last__lt=cutoff) | Q(last=None))
    latest_failures = FetchResult.objects.filter(
        ok=False, run__started_at__gte=timezone.now() - timedelta(hours=26)
    ).select_related("asset", "run")
    return context | {
        "dashboard": {
            "pages": pages.count(),
            "stale": list(stale.order_by("last")[:20].values_list("code", "last")),
            "stale_count": stale.count(),
            "failures": latest_failures[:20],
            "failure_count": latest_failures.count(),
            "paused": AdrConversion.objects.filter(status=AdrConversion.Status.PAUSED).select_related("asset"),
            "drafts": Draft.objects.count(),
            "runs": FetchRun.objects.all()[:RECENT_RUNS],
        }
    }
