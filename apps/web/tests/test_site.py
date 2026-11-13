import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.content import services
from apps.content.models import Comparison, Language, Page, Reviewer
from apps.content.tests.test_page import add_forecast
from apps.market.catalog import asset_rows, slug_for
from apps.market.models import Asset
from apps.web import caching, data


@pytest.fixture(autouse=True)
def memory_cache(settings):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "web"}}
    from django.core.cache import cache

    cache.clear()


@pytest.fixture
def seeded(db):
    call_command("seed_assets", verbosity=0)
    call_command("seed_templates", verbosity=0)
    call_command("seed_pages", verbosity=0)


def asset(code):
    return Asset.objects.select_related("asset_class").get(code=code)


@pytest.fixture
def btc(seeded):
    add_forecast(asset("BTC"), 80504.0)
    caching.bump()
    return asset("BTC")


def test_home_without_data_still_opens(db):
    response_ok = pytest.importorskip("django.test").Client().get("/")
    assert response_ok.status_code == 200


def test_small_site_urls_are_preserved():
    slugs = {r["code"]: slug_for(r) for r in asset_rows()}
    assert slugs["XAG"] == "silver-price-prediction"
    assert slugs["XAU"] == "gold-price-prediction"
    assert slugs["BTC"] == "bitcoin-price-prediction"
    assert slugs["XRP"] == "xrp-price-prediction"
    assert slugs["SOL"] == "solana-price-prediction"
    assert slugs["DOGE"] == "dogecoin-price-prediction"
    assert slugs["NVDA"] == "nvidia-stock-forecast"
    assert slugs["AMZN"] == "amazon-stock-price-prediction"


def test_every_asset_has_a_unique_slug():
    rows = asset_rows()
    pages = [slug_for(r) for r in rows]
    assert len(pages) == len(set(pages))
    assert all(s == s.lower() and " " not in s for s in pages)


def test_asset_page_renders_every_section(client, btc):
    html = client.get("/bitcoin-price-prediction/").content.decode()
    for marker in (
        "Bitcoin Price Prediction",
        'id="summary"',
        'id="chart"',
        'id="next-30-days"',
        'id="next-5-years"',
        'id="outlook"',
        'id="technical-analysis"',
        'id="drivers"',
        'id="history"',
        'id="investment"',
        'id="accuracy"',
        'id="faq"',
    ):
        assert marker in html, marker
    assert "$80,504" in html
    assert "<strong>" in html
    assert "**" not in html


def test_stock_pages_do_not_repeat_the_word(client, seeded):
    add_forecast(asset("BMW"), 60.0)
    html = client.get(asset("BMW").slug.join(("/", "/"))).content.decode()
    assert "stock stock" not in html


def test_page_is_noindex_before_launch(client, btc):
    assert 'content="noindex, nofollow"' in client.get("/bitcoin-price-prediction/").content.decode()


def test_page_has_canonical(client, btc):
    assert 'rel="canonical"' in client.get("/bitcoin-price-prediction/").content.decode()


def test_unknown_page_is_404_with_the_site_layout(client, btc):
    response = client.get("/no-such-asset/")
    assert response.status_code == 404
    assert b"Page not found" in response.content


def test_supporting_series_has_no_page(client, seeded):
    assert client.get(f"/{asset('BRENT').slug or 'brent'}/").status_code == 404


def test_hidden_section_disappears(client, btc):
    services.save_override(btc, Language.objects.get(code="en"), "show_faq", "0")
    assert 'id="faq"' not in client.get("/bitcoin-price-prediction/").content.decode()


def test_saving_text_reaches_the_cached_page(client, btc):
    assert "Fresh heading" not in client.get("/bitcoin-price-prediction/").content.decode()
    services.save_override(btc, Language.objects.get(code="en"), "h1", "Fresh heading")
    assert "Fresh heading" in client.get("/bitcoin-price-prediction/").content.decode()


def test_page_comes_from_the_cache(client, btc, django_assert_num_queries):
    client.get("/bitcoin-price-prediction/")
    with django_assert_num_queries(0):
        response = client.get("/bitcoin-price-prediction/")
    assert response.status_code == 200


def test_custom_block_appears_after_its_section(client, btc):
    btc.custom_blocks.create(
        language=Language.objects.get(code="en"), after_section="chart", title="My block", body="Hi"
    )
    html = client.get("/bitcoin-price-prediction/").content.decode()
    assert html.index('id="chart"') < html.index("My block") < html.index('id="next-30-days"')


def test_analysts_show_only_with_entries(client, btc):
    assert 'id="analysts"' not in client.get("/bitcoin-price-prediction/").content.decode()
    btc.analyst_targets.create(
        institution="Example Bank",
        kind="bank",
        target=100000,
        basis="end",
        horizon="2027",
        published_on="2026-10-01",
        source_title="Outlook",
        source_url="https://example.com/o",
    )
    html = client.get("/bitcoin-price-prediction/").content.decode()
    assert 'id="analysts"' in html and "Example Bank" in html and "https://example.com/o" in html


def test_home_and_hubs(client, btc):
    assert "Bitcoin" in client.get("/").content.decode()
    assert "Bitcoin" in client.get(reverse("hub_crypto")).content.decode()
    assert client.get(reverse("hub_metal")).status_code == 404  # nothing to show yet


def test_country_hub(client, seeded):
    add_forecast(asset("BMW"), 60.0)
    add_forecast(asset("AAPL"), 300.0)
    caching.bump()
    germany = client.get(reverse("hub_country", args=["germany"])).content.decode()
    assert "BMW" in germany and "Apple" not in germany.split("<main")[1].split("</main>")[0]
    assert client.get(reverse("hub_country", args=["mars"])).status_code == 404


def test_chart_data(client, btc):
    payload = client.get("/api/chart/BTC.json").json()
    assert payload["history"][-1][1] == 80504.0
    assert payload["forecast"]["consensus"]
    assert payload["forecast"]["low"][0][1] < payload["forecast"]["high"][0][1]
    assert client.get("/api/chart/NOPE.json").status_code == 404


def test_live_quotes_are_public_and_carry_no_keys(client, seeded):
    from django.core.cache import cache

    cache.set("live:AAPL", {"price": 349.5, "change_pct": 1.2, "time": 1}, 60)
    response = client.get("/api/live/")
    assert response.json() == {"AAPL": {"price": 349.5, "change_pct": 1.2, "time": 1}}


def test_accuracy_page(client, btc):
    html = client.get(reverse("accuracy")).content.decode()
    assert "Bitcoin" in html
    assert "close to chance" in html or "no better than chance" in html


def test_comparison(client, seeded):
    add_forecast(asset("BTC"), 80000.0)
    add_forecast(asset("ETH"), 2400.0)
    caching.bump()
    pair = Comparison.objects.get(left__code="BTC", right__code="ETH")
    html = client.get(reverse("comparison", args=[pair.slug])).content.decode()
    assert "Bitcoin" in html and "Ethereum" in html and "$2,400" in html
    assert pair.slug in client.get(reverse("comparisons")).content.decode()


def test_static_pages_and_author(client, seeded):
    for name in ("methodology", "about", "disclaimer", "privacy", "contact"):
        assert client.get(reverse(name)).status_code == 200
    Reviewer.objects.get(slug="margerie-holtz")
    assert b"Margerie Holtz" in client.get(reverse("author", args=["margerie-holtz"])).content


def test_guides_and_blog(client, seeded):
    english = Language.objects.get(code="en")
    assert b"Nothing published yet" in client.get(reverse("guides")).content
    Page.objects.create(
        kind="guide", slug="buy-gold", language=english, title="How to buy gold", body="<p>Text</p>", published=True
    )
    Page.objects.create(kind="blog", slug="draft", language=english, title="Draft post", body="x", published=False)
    assert b"How to buy gold" in client.get(reverse("guides")).content
    assert client.get(reverse("guide", args=["buy-gold"])).status_code == 200
    assert client.get(reverse("post", args=["draft"])).status_code == 404


def test_sparkline_and_direction():
    assert data.sparkline([1.0]) == {}
    assert data.sparkline([1.0, 2.0])["trend"] == "up"
    assert data.direction(0.01) == "up" and data.direction(-0.01) == "down" and data.direction(0) == "flat"


def test_extremes():
    from datetime import date

    bars = [(date(2026, 1, 1), 100), (date(2026, 1, 2), 120), (date(2026, 1, 3), 60)]
    found = data.extremes(bars)
    assert found["fall"] == pytest.approx(-0.5)
    assert found["move"] == pytest.approx(-0.5)


def test_history_rows_are_newest_first():
    from datetime import date

    bars = [(date(2025, 12, 31), 100), (date(2026, 1, 1), 110), (date(2026, 6, 1), 120)]
    rows = data.history_rows(bars)
    assert rows[0]["year"] == 2026
    assert rows[0]["change"] == pytest.approx(0.2)


def test_text_cannot_inject_html(client, btc):
    services.save_override(btc, Language.objects.get(code="en"), "h1", "<script>x</script>")
    assert "<script>x</script>" not in client.get("/bitcoin-price-prediction/").content.decode()


def test_crypto_headings_follow_the_crypto_template(client, btc):
    html = client.get("/bitcoin-price-prediction/").content.decode()
    for heading in (
        "Bitcoin forecast at a glance</h2>",
        "Short term Bitcoin daily price prediction</h2>",
        "BTC forecast for tomorrow and next week</h3>",
        "Bitcoin 5 year forecast</h2>",
        "Long term Bitcoin forecast for the next 10 years</h2>",
        "BTC technical analysis</h2>",
        "Bitcoin FAQ</h2>",
    ):
        assert heading in html, heading


def test_faq_questions_are_h3_and_match_the_schema(client, btc):
    import json
    import re

    html = client.get("/bitcoin-price-prediction/").content.decode()
    questions = re.findall(r'<h3 class="faq__q">(.*?)</h3>', html)
    assert questions
    block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    schema = json.loads(block.group(1))
    assert schema["@type"] == "FAQPage"
    assert len(schema["mainEntity"]) == len(questions)
    assert all(q["acceptedAnswer"]["text"] for q in schema["mainEntity"])


def test_faq_schema_cannot_break_out_of_the_script_tag():
    page = {"show": {"faq": True}, "faq": [{"title": "</script><b>", "text": "a & b"}]}
    text = data.faq_schema(page)
    assert "<" not in text and "&" not in text


def test_no_faq_schema_when_the_faq_is_hidden():
    assert data.faq_schema({"show": {"faq": False}, "faq": [{"title": "q", "text": "a"}]}) == ""


def test_sitemap_lists_public_pages_only(client, btc):
    response = client.get("/forecast-sitemap.xml")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/xml")
    body = response.content.decode()
    assert (
        "<loc>https://price-predictions.net/</loc>"
        in body.replace("http://testserver", "https://price-predictions.net")
        or "/</loc>" in body
    )
    assert "/bitcoin-price-prediction/</loc>" in body
    assert "/crypto/</loc>" in body
    assert "/accuracy/</loc>" in body
    assert "-old/" not in body and "/api/" not in body and "manage-" not in body
    assert "<lastmod>" in body


def test_robots_when_indexing_names_no_sitemap_or_admin(client, settings):
    settings.INDEXING = True
    body = client.get("/robots.txt").content.decode()
    assert "Allow: /" in body
    assert "Sitemap" not in body
    assert settings.ADMIN_URL.strip("/") not in body


def test_google_tag_manager_is_in_the_head(client, btc):
    for url in ("/", "/bitcoin-price-prediction/", "/accuracy/", "/no-such-page/"):
        html = client.get(url).content.decode()
        head = html.split("</head>", 1)[0]
        assert "googletagmanager.com/gtm.js?id=GTM-P2ZGFMR3" in head, url
