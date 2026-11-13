"""The XML sitemap at /forecast-sitemap.xml: every public, indexable page (not the frozen archive copies)."""

from datetime import date
from xml.sax.saxutils import escape

from django.conf import settings
from django.db.models import Max
from django.urls import reverse

from apps.content.models import Comparison, Page, Reviewer
from apps.market.models import Asset

from . import data

STATIC_SLUGS = ("methodology", "about", "contact", "disclaimer", "privacy")  # the routed static pages


def entries() -> list[tuple[str, date | None]]:
    """(path, last modified) for every page that should be indexed."""
    runs = dict(data.latest_runs().values("asset_id").annotate(last=Max("run_date")).values_list("asset_id", "last"))
    newest = max(runs.values(), default=None)
    assets = Asset.objects.filter(enabled=True, series_of=None, pk__in=runs).select_related("asset_class")

    out = [(reverse("home"), newest)]
    classes = {a.asset_class.code for a in assets}
    for code in data.CLASS_ORDER:
        if code in classes:
            out.append((f"/{data.CLASS_PAGES[code][0]}/", newest))
    countries = {a.country for a in assets if a.asset_class.code == "stock"}
    for slug, (_heading, country) in data.COUNTRY_PAGES.items():
        if country in countries:
            out.append((reverse("hub_country", args=[slug]), newest))
    out += [(data.asset_url(a), runs[a.pk]) for a in assets.order_by("asset_class__code", "name")]
    out.append((reverse("accuracy"), newest))

    pairs = Comparison.objects.filter(enabled=True, left__enabled=True, right__enabled=True)
    if pairs.exists():
        out.append((reverse("comparisons"), newest))
        out += [(reverse("comparison", args=[p.slug]), newest) for p in pairs.order_by("slug")]

    pages = Page.objects.filter(published=True, language__code="en")
    for kind, listing in ((Page.Kind.GUIDE, "guides"), (Page.Kind.BLOG, "blog")):
        chosen = pages.filter(kind=kind)
        if chosen.exists():
            out.append((reverse(listing), max(p.updated_at.date() for p in chosen)))
            out += [(p.get_absolute_url(), p.updated_at.date()) for p in chosen.order_by("slug")]
    out += [
        (p.get_absolute_url(), p.updated_at.date())
        for p in pages.filter(kind=Page.Kind.STATIC, slug__in=STATIC_SLUGS).order_by("slug")
    ]
    out += [(reverse("author", args=[r.slug]), None) for r in Reviewer.objects.order_by("slug")]
    return out


def xml() -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, modified in entries():
        lastmod = f"<lastmod>{modified.isoformat()}</lastmod>" if modified else ""
        lines.append(f"<url><loc>{escape(settings.SITE_URL + path)}</loc>{lastmod}</url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"
