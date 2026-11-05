"""The output rule (TECHNICAL-TASK §7.1): manual value, else class template, else nothing.

One function builds everything a page says, so milestone 6 only has to lay it out.
"""

from .context import Context, build, year_values
from .fields import FIELDS, FLAG, LINE, PAIRS, SECTIONS
from .models import Override, Template
from .templating import render


class LanguageNotReady(RuntimeError):
    """Templates are missing, so this language must not be published for the page."""


def sources(asset, language_code: str) -> dict[str, tuple[str, str]]:
    """Field key to (text, where it came from), applying the rule. English never fills in for German."""
    out = {
        t.field: (t.body, "template")
        for t in Template.objects.filter(asset_class=asset.asset_class, language__code=language_code)
    }
    for o in Override.objects.filter(asset=asset, language__code=language_code):
        out[o.field] = (o.value, "override")
    return out


def shape(field, paragraphs: list[str]):
    if field.kind == LINE:
        return paragraphs[0] if paragraphs else ""
    if field.kind == PAIRS:
        return [dict(zip(("title", "text"), p.split(" :: ", 1), strict=True)) for p in paragraphs]
    return paragraphs


def build_page(asset, language_code: str = "en") -> dict:
    """Every field of the page with today's values in it."""
    context: Context = build(asset, language_code)
    texts = sources(asset, language_code)
    missing = [f.key for f in FIELDS if not f.optional and f.key not in texts]
    if missing:
        raise LanguageNotReady(f"{asset.code}/{language_code}: no text for {', '.join(missing[:5])}")

    page = {}
    for field in FIELDS:
        if field.year_scope or field.kind == FLAG:
            continue
        text = texts.get(field.key, ("", ""))[0]
        page[field.key] = shape(field, render(text, context.values, context.flags, f"{context.seed}|{field.key}"))

    years = []
    for year in sorted({p.target.year for p in context.monthly.get("consensus", [])}):
        scoped = year_values(context, year)
        if scoped is None:
            continue
        values = context.values | scoped
        seed = f"{context.seed}|{year}"
        years.append(
            {
                "year": year,
                "heading": next(iter(render(texts["h_year"][0], values, context.flags, f"{seed}|h")), ""),
                "paragraphs": render(texts["year_text"][0], values, context.flags, f"{seed}|t"),
            }
        )
    page["years"] = years
    page["show"] = {s: texts.get(f"show_{s}", ("1", ""))[0].strip() != "0" for s in SECTIONS}
    page["sources"] = {key: source for key, (_, source) in texts.items()}
    return page
