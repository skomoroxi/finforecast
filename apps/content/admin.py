from django import forms
from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path
from unfold.admin import ModelAdmin, TabularInline

from . import csvio, drafts, services, validation
from .editor import editor_view
from .models import (
    AnalystTarget,
    CustomBlock,
    Draft,
    Language,
    Override,
    Reviewer,
    ReviewerBio,
    Revision,
    Template,
)

PREVIEW = 80


class CheckedForm(forms.ModelForm):
    """Unknown substitutions and bad structure stop the save. Warnings are shown after it."""

    text_field = ""
    check_field = ""

    def clean(self):
        cleaned = super().clean()
        field_key = self.check_field or cleaned.get("field", "")
        report = validation.full_check(field_key, cleaned.get(self.text_field, ""))
        for error in report.errors:
            self.add_error(self.text_field, error)
        self.warnings = report.warnings
        return cleaned


class TemplateForm(CheckedForm):
    text_field = "body"

    class Meta:
        model = Template
        fields = ["asset_class", "language", "field", "body"]


class OverrideForm(CheckedForm):
    text_field = "value"

    class Meta:
        model = Override
        fields = ["asset", "language", "field", "value"]


class CustomBlockForm(CheckedForm):
    text_field = "body"
    check_field = "intro"  # the same rules as any free text field

    class Meta:
        model = CustomBlock
        fields = ["asset", "language", "after_section", "title", "body", "order", "enabled"]


class UploadForm(forms.Form):
    file = forms.FileField()


class CsvAdmin(ModelAdmin):
    change_list_template = "admin/content/change_list_csv.html"
    csv_name = ""

    def csv_export(self) -> str:
        raise NotImplementedError

    def csv_import(self, text: str, user):
        raise NotImplementedError

    def get_urls(self):
        return [
            path("export-csv/", self.admin_site.admin_view(self.export_view), name=f"{self.csv_name}_export"),
            path("import-csv/", self.admin_site.admin_view(self.import_view), name=f"{self.csv_name}_import"),
            *super().get_urls(),
        ]

    def export_view(self, request):
        response = HttpResponse(self.csv_export(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{self.csv_name}.csv"'
        return response

    def import_view(self, request):
        form = UploadForm(request.POST or None, request.FILES or None)
        report = None
        if request.method == "POST" and form.is_valid():
            report = self.csv_import(form.cleaned_data["file"].read().decode("utf-8-sig"), request.user)
        context = self.admin_site.each_context(request) | {
            "title": f"Import {self.opts.verbose_name_plural}",
            "form": form,
            "report": report,
        }
        return render(request, "admin/content/import_csv.html", context)


@admin.register(Language)
class LanguageAdmin(ModelAdmin):
    list_display = ["code", "name", "enabled", "country"]


@admin.register(Template)
class TemplateAdmin(CsvAdmin):
    form = TemplateForm
    csv_name = "templates"
    list_display = ["asset_class", "language", "field", "preview", "updated_at"]
    list_filter = ["asset_class", "language", "field"]
    search_fields = ["body"]

    def csv_export(self):
        return csvio.export_templates()

    def csv_import(self, text, user):
        return csvio.import_templates(text, user)

    @admin.display(description="Text")
    def preview(self, obj):
        return obj.body[:PREVIEW]

    def save_model(self, request, obj, form, change):
        services.save_template(obj.asset_class, obj.language, obj.field, obj.body, request.user)
        for warning in form.warnings:
            messages.warning(request, warning)


@admin.register(Override)
class OverrideAdmin(CsvAdmin):
    form = OverrideForm
    csv_name = "manual-values"
    list_display = ["asset", "language", "field", "preview", "updated_by", "updated_at"]
    list_filter = ["language", "field", "asset__asset_class"]
    search_fields = ["asset__code", "asset__name", "value"]
    actions = ["reset_to_template"]

    def get_urls(self):
        editor = self.admin_site.admin_view(editor_view)
        return [
            path("editor/<str:code>/<str:language_code>/", editor, name="content_editor"),
            *super().get_urls(),
        ]

    def csv_export(self):
        return csvio.export_overrides()

    def csv_import(self, text, user):
        return csvio.import_overrides(text, user)

    @admin.display(description="Text")
    def preview(self, obj):
        return obj.value[:PREVIEW]

    def save_model(self, request, obj, form, change):
        services.save_override(obj.asset, obj.language, obj.field, obj.value, request.user)
        for warning in form.warnings:
            messages.warning(request, warning)

    def delete_model(self, request, obj):
        services.reset_override(obj, request.user)

    def delete_queryset(self, request, queryset):
        for override in queryset:
            services.reset_override(override, request.user)

    @admin.action(description="Reset to template")
    def reset_to_template(self, request, queryset):
        count = queryset.count()
        self.delete_queryset(request, queryset)
        self.message_user(request, f"{count} reset to the template.", messages.SUCCESS)


class ReviewerBioInline(TabularInline):
    model = ReviewerBio
    extra = 0


@admin.register(Reviewer)
class ReviewerAdmin(ModelAdmin):
    list_display = ["name", "job_title", "slug"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [ReviewerBioInline]


@admin.register(CustomBlock)
class CustomBlockAdmin(ModelAdmin):
    form = CustomBlockForm
    list_display = ["asset", "language", "title", "after_section", "order", "enabled"]
    list_filter = ["language", "enabled"]
    search_fields = ["asset__code", "title", "body"]


@admin.register(AnalystTarget)
class AnalystTargetAdmin(ModelAdmin):
    list_display = [
        "asset",
        "institution",
        "kind",
        "target",
        "target_low",
        "target_high",
        "horizon",
        "published_on",
        "show",
    ]
    list_filter = ["kind", "show", "asset"]
    search_fields = ["asset__code", "institution", "source_title"]


@admin.register(Revision)
class RevisionAdmin(ModelAdmin):
    list_display = ["created_at", "kind", "asset_class", "asset", "language", "field", "removed", "note", "user"]
    list_filter = ["kind", "language", "field"]
    search_fields = ["asset__code", "value"]
    actions = ["roll_back"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.action(description="Roll back to this version")
    def roll_back(self, request, queryset):
        for revision in queryset.order_by("created_at"):
            services.roll_back(revision, request.user)
        self.message_user(request, f"{queryset.count()} rolled back.", messages.SUCCESS)


@admin.register(Draft)
class DraftAdmin(ModelAdmin):
    list_display = ["asset", "language", "field", "preview", "has_figures", "model_name", "created_at"]
    list_filter = ["language", "field", "asset__asset_class"]
    search_fields = ["asset__code", "asset__name", "value"]
    actions = ["approve"]

    @admin.display(description="Text")
    def preview(self, obj):
        return obj.value[:PREVIEW]

    @admin.display(description="Has figures", boolean=True)
    def has_figures(self, obj):
        return drafts.has_digits(obj.value)

    @admin.action(description="Approve and publish")
    def approve(self, request, queryset):
        count = queryset.count()
        for draft in queryset.select_related("asset", "language"):
            services.approve_draft(draft, request.user)
        self.message_user(request, f"{count} approved and published.", messages.SUCCESS)

    def has_add_permission(self, request):
        return False
