import json

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _

from apps.content.context import NoForecast
from apps.content.models import Comparison, Page, Reviewer
from apps.market.models import Asset

from . import archive, data, sitemap
from .caching import cached_page, version

CHART_SECONDS = 6 * 3600
LIVE_EDGE_SECONDS = 60


def seo(title: str, description: str = "") -> dict:
    return {"meta_title": title, "meta_description": description}


@cached_page
def home(request):
    groups = data.cards_by_class()
    for group in groups:
        group["more"] = len(group["cards"]) > 8
        group["cards"] = group["cards"][:8]
    title = _("Price Predictions for Crypto, Stocks, Metals & Oil | FinForecast")
    description = _(
        "Daily price predictions for cryptocurrencies, stocks, metals, oil and currency pairs: "
        "30-day, monthly and long-term forecasts from three statistical models."
    )
    return render(request, "web/home.html", seo(title, description) | {"groups": groups})


def class_view(request, code, country=None):
    path, title = data.CLASS_PAGES[code]
    items = [c for c in data.cards() if c["class"] == code]
    heading = _(title)
    if country:
        heading, country_code = data.COUNTRY_PAGES[country]
        heading = _(heading)
        items = [c for c in items if c["country"] == country_code]
    if not items:
        raise Http404
    context = seo(f"{heading} | FinForecast") | {
        "heading": heading,
        "cards": items,
        "code": code,
        "countries": data.COUNTRY_PAGES.items() if code == "stock" else (),
    }
    return render(request, "web/hub.html", context)


@cached_page
def class_hub(request, code):
    return class_view(request, code)


@cached_page
def country_hub(request, country):
    if country not in data.COUNTRY_PAGES:
        raise Http404
    return class_view(request, "stock", country)


@cached_page
def asset_page(request, slug):
    asset = get_object_or_404(
        Asset.objects.select_related("asset_class", "technicals", "adr"), slug=slug, enabled=True, series_of=None
    )
    try:
        context = data.asset_page(asset)
    except NoForecast:
        raise Http404 from None
    page = context["page"]
    return render(request, "web/asset.html", seo(page["title"], page["meta_description"]) | context)


@cached_page
def accuracy(request):
    title = _("How Accurate Are Our Price Forecasts? | FinForecast")
    return render(request, "web/accuracy.html", seo(title) | data.accuracy_overview())


@cached_page
def comparison(request, slug):
    pair = get_object_or_404(Comparison.objects.select_related("left", "right"), slug=slug, enabled=True)
    title = _("%(left)s vs %(right)s Forecast | FinForecast") % {"left": pair.left.name, "right": pair.right.name}
    left = Asset.objects.select_related("asset_class").get(pk=pair.left_id)
    right = Asset.objects.select_related("asset_class").get(pk=pair.right_id)
    return render(request, "web/compare.html", seo(title) | {"pair": pair} | data.compare(left, right))


@cached_page
def comparisons(request):
    pairs = Comparison.objects.filter(enabled=True).select_related("left", "right")
    return render(request, "web/compare_list.html", seo(_("Forecast Comparisons | FinForecast")) | {"pairs": pairs})


def article_list(request, kind, heading):
    pages = Page.objects.filter(kind=kind, published=True, language__code="en").select_related("reviewer")
    return render(
        request, "web/article_list.html", seo(f"{heading} | FinForecast") | {"heading": heading, "pages": pages}
    )


@cached_page
def guides(request):
    return article_list(request, Page.Kind.GUIDE, _("Guides"))


@cached_page
def blog(request):
    return article_list(request, Page.Kind.BLOG, _("Blog"))


def show_page(request, kind, slug):
    page = get_object_or_404(
        Page.objects.select_related("reviewer"), kind=kind, slug=slug, published=True, language__code="en"
    )
    assets = page.assets.filter(enabled=True, series_of=None)
    return render(
        request,
        "web/page.html",
        seo(page.seo_title or f"{page.title} | FinForecast", page.meta_description) | {"page": page, "assets": assets},
    )


@cached_page
def guide(request, slug):
    return show_page(request, Page.Kind.GUIDE, slug)


@cached_page
def post(request, slug):
    return show_page(request, Page.Kind.BLOG, slug)


@cached_page
def static_page(request, slug):
    return show_page(request, Page.Kind.STATIC, slug)


@cached_page
def author(request, slug):
    reviewer = get_object_or_404(Reviewer, slug=slug)
    bio = reviewer.bios.filter(language__code="en").first()
    title = f"{reviewer.name}, {reviewer.job_title} | FinForecast"
    return render(request, "web/author.html", seo(title) | {"reviewer": reviewer, "bio": bio})


def chart_json(request, code):
    key = f"web:chart:{version()}:{code}"
    body = cache.get(key)
    if body is None:
        asset = get_object_or_404(Asset, code=code, enabled=True, series_of=None)
        body = json.dumps(data.chart_data(asset), separators=(",", ":"))
        cache.set(key, body, CHART_SECONDS)
    response = HttpResponse(body, content_type="application/json")
    response["Cache-Control"] = "public, max-age=3600"
    return response


def live_quotes(request):
    """Delayed quotes for US-traded symbols, refreshed by the worker. No keys reach the browser."""
    codes = Asset.objects.filter(enabled=True).exclude(live_symbol="").values_list("code", flat=True)
    keys = {f"live:{code}": code for code in codes}
    found = cache.get_many(keys)
    response = JsonResponse({keys[k]: v for k, v in found.items()})
    response["Cache-Control"] = f"public, max-age={LIVE_EDGE_SECONDS}, s-maxage={LIVE_EDGE_SECONDS}"
    return response


def robots(request):
    # The sitemap (/forecast-sitemap.xml) is submitted to search engines directly, not announced here (owner's
    # choice). The admin path is not listed either: robots.txt is public and would reveal it; the admin is noindex.
    if settings.INDEXING:
        body = "User-agent: *\nAllow: /\nDisallow: /api/\n"
    else:
        body = "# Pre-launch: nothing is indexed yet.\nUser-agent: *\nDisallow: /\n"
    return HttpResponse(body, content_type="text/plain")


def sitemap_xml(request):
    key = f"web:sitemap:{version()}"
    body = cache.get(key)
    if body is None:
        body = sitemap.xml()
        cache.set(key, body, CHART_SECONDS)
    response = HttpResponse(body, content_type="application/xml; charset=utf-8")
    response["Cache-Control"] = "public, max-age=3600"
    return response


def archived_page(request, slug):
    """A frozen copy of a page from before a content change (apps/web/archive.py); never indexed."""
    if slug not in archive.PAGES:
        raise Http404
    response = HttpResponse(archive.html(slug))
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response
