"""The page editor: one asset, one language, every field and where its text comes from (TECHNICAL-TASK §7.4)."""

from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.market.models import Asset

from . import drafts as ai
from . import services, validation
from .context import NoForecast, build, year_values
from .fields import FIELDS, FLAG, Field
from .models import CustomBlock, Draft, Language, Override, Reviewer, Template
from .page import shape
from .templating import render as render_text

SECTION_TITLES = {
    "seo": "SEO",
    "headings": "Headings",
    "text": "Texts",
    "lists": "Factors, arguments and FAQ",
    "other": "Author and image",
    "visibility": "Sections shown",
}


def preview(field: Field, text: str, context):
    """How the field reads today, or None when it cannot be worked out yet."""
    if context is None or field.kind == FLAG or not text:
        return None
    values = context.values
    if field.year_scope:
        years = sorted({p.target.year for p in context.monthly.get("consensus", [])})
        scoped = year_values(context, years[-1]) if years else None
        if scoped is None:
            return None
        values = values | scoped
    result = shape(field, render_text(text, values, context.flags, f"{context.seed}|{field.key}"))
    if isinstance(result, list):
        return [f"{r['title']}: {r['text']}" if isinstance(r, dict) else r for r in result]
    return [result]


def rows(asset, language, context, unsaved: dict | None = None) -> list[dict]:
    templates = dict(
        Template.objects.filter(asset_class=asset.asset_class, language=language).values_list("field", "body")
    )
    overrides = {o.field: o for o in Override.objects.filter(asset=asset, language=language)}
    pending = {d.field: d for d in Draft.objects.filter(asset=asset, language=language)}
    out = []
    for field in FIELDS:
        override = overrides.get(field.key)
        template = templates.get(field.key, "")
        text = override.value if override else template
        draft = pending.get(field.key)
        rejected = (unsaved or {}).get(field.key)
        out.append(
            {
                "field": field,
                "state": "override" if override else ("template" if template else "empty"),
                "text": text if rejected is None else rejected,
                "open": rejected is not None or draft is not None,
                "template": template,
                "preview": preview(field, text, context),
                "draft": draft,
                "draft_has_figures": ai.has_digits(draft.value) if draft else False,
                "shown": text.strip() != "0",
            }
        )
    return out


def handle_post(request, asset, language) -> dict:
    """Returns the text of a refused save, so the person keeps what they typed."""
    key, text = request.POST.get("field", ""), request.POST.get("value", "")
    action = request.POST.get("action")
    override = Override.objects.filter(asset=asset, language=language, field=key).first()
    if action == "reset" and override:
        services.reset_override(override, request.user)
        messages.success(request, f"{key}: back to the template.")
    elif action == "approve":
        draft = Draft.objects.filter(asset=asset, language=language, field=key).first()
        if draft:
            services.approve_draft(draft, request.user)
            messages.success(request, f"{key}: draft approved and published.")
    elif action == "reject":
        Draft.objects.filter(asset=asset, language=language, field=key).delete()
        messages.success(request, f"{key}: draft discarded.")
    elif action == "save":
        report = validation.full_check(key, text)
        for error in report.errors:
            messages.error(request, f"{key}: {error}. Not saved.")
        if report.errors:
            return {key: text}
        services.save_override(asset, language, key, text, request.user)
        messages.success(request, f"{key}: saved.")
        for warning in report.warnings:
            messages.warning(request, f"{key}: {warning}.")
    return {}


def editor_view(request, code: str, language_code: str = "en"):
    asset = get_object_or_404(Asset.objects.select_related("asset_class"), code=code, series_of=None)
    language = get_object_or_404(Language, code=language_code)
    unsaved = {}
    if request.method == "POST":
        unsaved = handle_post(request, asset, language)
        if not unsaved:
            return redirect(request.path + "#" + request.POST.get("field", ""))

    try:
        context = build(asset, language_code)
    except NoForecast:
        context = None
    field_rows = rows(asset, language, context, unsaved)
    sections = [
        {"title": title, "rows": [r for r in field_rows if r["field"].section == key]}
        for key, title in SECTION_TITLES.items()
    ]
    return render(
        request,
        "admin/content/editor.html",
        admin.site.each_context(request)
        | {
            "title": f"{asset.name}: page content",
            "asset": asset,
            "language": language,
            "languages": Language.objects.order_by("-enabled", "code"),
            "sections": sections,
            "reviewers": Reviewer.objects.values_list("name", flat=True),
            "blocks": CustomBlock.objects.filter(asset=asset, language=language),
            "block_add": reverse("admin:content_customblock_add"),
            "analysts_url": reverse("admin:content_analysttarget_changelist") + f"?asset__id__exact={asset.pk}",
            "no_forecast": context is None,
            "manual_count": sum(r["state"] == "override" for r in field_rows),
            "draft_count": sum(r["draft"] is not None for r in field_rows),
        },
    )
