from django.contrib import admin, messages
from django.db.models import Max
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline

from . import tasks
from .models import AdrConversion, Asset, AssetClass, FetchResult, FetchRun


def rerun(task: str, codes: list[str]) -> None:
    """Queue the same kind of job again for these assets."""
    if task.startswith("forecast"):
        from apps.forecasts.tasks import forecast_codes

        forecast_codes.delay(codes)
    elif task == "ai-draft":
        from apps.content.tasks import create_drafts

        create_drafts.delay(codes)
    elif task == "adr-ratio":
        tasks.recalc_codes.delay(codes)
    else:
        tasks.update_codes.delay(codes, full=task == "backfill")


@admin.register(AssetClass)
class AssetClassAdmin(ModelAdmin):
    list_display = ["code", "name", "calendar", "default_unit", "max_daily_change", "max_annual_drift"]


@admin.register(Asset)
class AssetAdmin(ModelAdmin):
    list_display = ["code", "name", "asset_class", "source", "symbol", "currency", "enabled", "last_bar", "page"]
    list_filter = ["asset_class", "source", "enabled"]
    search_fields = ["code", "name", "symbol"]
    actions = ["update_now", "reload_history", "create_ai_drafts"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(last_bar_date=Max("bars__date"))

    @admin.display(description="Last price", ordering="last_bar_date")
    def last_bar(self, obj):
        return obj.last_bar_date

    @admin.display(description="Content")
    def page(self, obj):
        if obj.series_of_id:
            return "-"
        return format_html('<a href="{}">Edit page</a>', reverse("admin:content_editor", args=[obj.code, "en"]))

    @admin.action(description="Update prices now")
    def update_now(self, request, queryset):
        tasks.update_codes.delay(list(queryset.values_list("code", flat=True)))
        self.message_user(request, "Queued. See Fetch runs for the result.", messages.SUCCESS)

    @admin.action(description="Reload full history")
    def reload_history(self, request, queryset):
        tasks.update_codes.delay(list(queryset.values_list("code", flat=True)), full=True)
        self.message_user(request, "Queued. See Fetch runs for the result.", messages.SUCCESS)

    @admin.action(description="Create AI drafts (English)")
    def create_ai_drafts(self, request, queryset):
        from apps.content.tasks import create_drafts

        create_drafts.delay(list(queryset.values_list("code", flat=True)))
        self.message_user(request, "Queued. See Fetch runs, then Drafts.", messages.SUCCESS)


@admin.register(AdrConversion)
class AdrConversionAdmin(ModelAdmin):
    list_display = ["asset", "adr_asset", "xetra_symbol", "ratio_auto", "ratio_manual", "status", "ratio_updated_at"]
    list_filter = ["status"]
    readonly_fields = ["ratio_auto", "ratio_candidate", "ratio_updated_at", "status"]
    actions = ["accept_candidate"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if "ratio_manual" in form.changed_data:
            tasks.rebuild_adr.delay(obj.asset.code)

    @admin.action(description="Accept the new ratio")
    def accept_candidate(self, request, queryset):
        accepted = 0
        for conv in queryset.exclude(ratio_candidate=None):
            conv.ratio_auto, conv.ratio_candidate = conv.ratio_candidate, None
            conv.status = AdrConversion.Status.OK
            conv.save(update_fields=["ratio_auto", "ratio_candidate", "status"])
            tasks.rebuild_adr.delay(conv.asset.code)
            accepted += 1
        self.message_user(request, f"{accepted} accepted, prices are being rebuilt.", messages.SUCCESS)


class FetchResultInline(TabularInline):
    model = FetchResult
    extra = 0
    can_delete = False
    fields = ["asset", "ok", "source", "bars", "last_date", "message"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(FetchRun)
class FetchRunAdmin(ModelAdmin):
    list_display = ["task", "started_at", "finished_at", "ok_count", "error_count"]
    list_filter = ["task"]
    inlines = [FetchResultInline]
    actions = ["rerun_failed"]

    @admin.action(description="Run the failed assets again")
    def rerun_failed(self, request, queryset):
        count = 0
        for run in queryset:
            codes = list(run.results.filter(ok=False).values_list("asset__code", flat=True))
            if codes:
                rerun(run.task, codes)
                count += len(codes)
        self.message_user(request, f"{count} assets queued.", messages.SUCCESS)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
