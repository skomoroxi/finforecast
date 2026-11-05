import csv

from django.contrib import admin
from django.http import HttpResponse
from unfold.admin import ModelAdmin

from .models import ForecastAccuracy, ForecastRun, TechnicalSnapshot


class ReadOnlyAdmin(ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ForecastRun)
class ForecastRunAdmin(ReadOnlyAdmin):
    list_display = ["asset", "run_date", "data_date", "last_close", "model_version", "created_at"]
    list_filter = ["asset__asset_class", "run_date"]
    search_fields = ["asset__code", "asset__name"]
    date_hierarchy = "run_date"


@admin.register(ForecastAccuracy)
class ForecastAccuracyAdmin(ReadOnlyAdmin):
    list_display = [
        "asset",
        "method",
        "horizon",
        "basis",
        "window_days",
        "mape",
        "mae",
        "direction_pct",
        "in_range_pct",
        "bias_pct",
        "samples",
    ]
    list_filter = ["basis", "method", "horizon", "window_days", "asset__asset_class"]
    search_fields = ["asset__code", "asset__name"]
    actions = ["export_csv"]

    @admin.action(description="Export selected rows to CSV")
    def export_csv(self, request, queryset):
        fields = [f.name for f in ForecastAccuracy._meta.fields if f.name not in ("id", "asset")]
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="forecast-accuracy.csv"'
        writer = csv.writer(response)
        writer.writerow(["asset", *fields])
        for row in queryset.select_related("asset"):
            writer.writerow([row.asset.code, *[getattr(row, f) for f in fields]])
        return response


@admin.register(TechnicalSnapshot)
class TechnicalSnapshotAdmin(ReadOnlyAdmin):
    list_display = ["asset", "run_date", "ohlc_basis"]
    list_filter = ["ohlc_basis"]
    search_fields = ["asset__code", "asset__name"]
