import re
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.admin import site
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.content import csvio, drafts, page, services
from apps.content.models import Draft, Language, Override, Revision, Template
from apps.forecasts.models import ForecastAccuracy, ForecastPoint, ForecastRun, TechnicalSnapshot
from apps.market.models import Asset, AssetClass, PriceBar


def add_forecast(asset, price=100.0):
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    for offset, close in ((2, price * 0.99), (1, price)):
        day = today - timedelta(days=offset)
        PriceBar.objects.create(
            asset=asset, date=day, close=Decimal(str(close)), avg=Decimal(str(close)), source="twelvedata"
        )
    methods = {
        "arima": {"status": "ok", "params": {}},
        "reversion": {"status": "ok", "params": {"deviation_from_trend_pct": 25.0}},
        "montecarlo": {"status": "ok", "params": {"mu_daily": 0.001}},
    }
    run = ForecastRun.objects.create(
        asset=asset, run_date=today, data_date=yesterday, last_close=price, model_version="1.1", methods=methods
    )
    rows = []

    def point(method, horizon, target, value):
        rows.append(
            ForecastPoint(
                run_date=today,
                run=run,
                asset=asset,
                method=method,
                horizon=horizon,
                target=target,
                value=value,
                p10=value * 0.8,
                p90=value * 1.2,
            )
        )

    for day in range(1, 31):
        point("consensus", "daily", today + timedelta(days=day), price * (1 + day / 300))
    for year in range(today.year, 2031):
        for month in range(today.month if year == today.year else 1, 13):
            for method, factor in (("consensus", 1), ("arima", 1), ("reversion", 0.9), ("montecarlo", 1.1)):
                point(
                    method,
                    "monthly",
                    today.replace(year=year, month=month, day=1),
                    price * factor * (1 + (year - 2026) / 10),
                )
    for year in range(2031, 2036):
        for method, factor in (("consensus", 1), ("reversion", 0.8), ("montecarlo", 1.2)):
            point(method, "yearly", today.replace(year=year, month=1, day=1), price * factor * 1.6)
    ForecastPoint.objects.bulk_create(rows)
    summary = {"overall": {"verdict": "buy"}}
    frame = {
        "summary": summary,
        "oscillators": [{"name": "rsi_14", "value": 61.5, "action": "buy"}],
        "moving_averages": [{"period": 200, "simple": {"value": 90.0, "action": "buy"}}],
    }
    TechnicalSnapshot.objects.create(
        asset=asset,
        run_date=today,
        ohlc_basis="full",
        timeframes={"daily": frame, "weekly": frame, "monthly": frame},
    )
    for horizon, mape in (("1d", 2.0), ("7d", 5.0), ("30d", 11.0)):
        ForecastAccuracy.objects.create(
            asset=asset,
            method="consensus",
            horizon=horizon,
            basis="backtest",
            mape=mape,
            mae=1,
            samples=50,
            computed_on=today,
        )


@pytest.fixture
def seeded(db):
    call_command("seed_assets", verbosity=0)
    call_command("seed_templates", verbosity=0)


@pytest.fixture
def btc(seeded):
    asset = Asset.objects.select_related("asset_class").get(code="BTC")
    add_forecast(asset)
    return Asset.objects.select_related("asset_class").get(code="BTC")


def english():
    return Language.objects.get(code="en")


def flat(built) -> str:
    return str(built)


def test_default_template_fills_the_page(btc):
    built = page.build_page(btc)
    assert built["title"].startswith("Bitcoin Price Prediction")
    assert built["reviewer"]["name"] == "Margerie Holtz"
    assert "$100.00" in built["summary"][0] or "$100.0" in built["summary"][0]
    assert built["show"]["faq"] is True
    assert built["years"][0]["year"] == timezone.now().year
    assert not re.search(r"{[A-Za-z0-9_]+}", flat(built))
    assert "None" not in flat(built)


def test_text_and_table_share_their_numbers(btc):
    built = page.build_page(btc)
    run = ForecastRun.objects.get(asset=btc, model_version="1.1")
    last = ForecastPoint.objects.filter(run=run, horizon="daily", method="consensus").order_by("target").last()
    assert f"${last.value:.2f}" in " ".join(built["next30"])


def test_manual_value_wins_and_uses_variables(btc):
    services.save_override(btc, english(), "h1", "My heading at {price}")
    built = page.build_page(btc)
    assert built["h1"].startswith("My heading at $")
    assert built["sources"]["h1"] == "override"
    assert built["sources"]["h_ta"] == "template"


def test_reset_returns_to_the_template(btc):
    override = services.save_override(btc, english(), "h1", "Mine")
    services.reset_override(override)
    assert page.build_page(btc)["h1"].endswith("(BTC)")
    assert Revision.objects.filter(field="h1", removed=True, value="Mine").exists()


def test_an_override_only_touches_its_own_asset(btc):
    eth = Asset.objects.select_related("asset_class").get(code="ETH")
    add_forecast(eth)
    services.save_override(btc, english(), "h1", "Mine")
    assert page.build_page(eth)["h1"] != "Mine"


def test_template_edit_reaches_every_asset_without_an_override(btc):
    services.save_template(btc.asset_class, english(), "h1", "New for {name}")
    assert page.build_page(btc)["h1"] == "New for Bitcoin"


def test_english_never_fills_in_for_german(btc):
    with pytest.raises(page.LanguageNotReady):
        page.build_page(btc, "de")


def test_a_hidden_section(btc):
    services.save_override(btc, english(), "show_faq", "0")
    assert page.build_page(btc)["show"]["faq"] is False


def test_faq_shows_one_answer_for_the_goal_question(btc):
    goal = [item for item in page.build_page(btc)["faq"] if "reach" in item["title"]]
    assert len(goal) == 1


def test_trend_sentence_follows_the_data(btc):
    assert any("above its long-run trend" in p for p in page.build_page(btc)["outlook"])


def test_missing_accuracy_drops_only_that_text(btc):
    ForecastAccuracy.objects.all().delete()
    built = page.build_page(btc)
    assert built["accuracy"] == []
    assert not any("accurate" in item["title"] for item in built["faq"])


def test_german_share_explains_its_price(seeded):
    bmw = Asset.objects.select_related("asset_class").get(code="BMW")
    add_forecast(bmw)
    built = page.build_page(Asset.objects.select_related("asset_class").get(code="BMW"))
    assert "BMWKY" in built["price_note"][0]
    assert "€" in built["summary"][0]


def test_exchange_rate_has_no_currency_sign(seeded):
    pair = Asset.objects.select_related("asset_class").get(code="EURUSD")
    add_forecast(pair, price=1.1224)
    built = page.build_page(Asset.objects.select_related("asset_class").get(code="EURUSD"))
    assert "1.1224" in built["summary"][0]
    assert "$" not in built["summary"][0]


def test_every_class_renders(seeded):
    for code in ("ETH", "AAPL", "SPY", "EURUSD", "XAU", "WTI"):
        asset = Asset.objects.select_related("asset_class").get(code=code)
        add_forecast(asset)
        built = page.build_page(Asset.objects.select_related("asset_class").get(code=code))
        assert not re.search(r"{[A-Za-z0-9_]+}", flat(built))
        assert built["drivers"] and built["bull"] and built["bear"] and built["risks"]


def test_history_and_rollback(btc):
    services.save_override(btc, english(), "h1", "First")
    services.save_override(btc, english(), "h1", "Second")
    first = Revision.objects.filter(field="h1", value="First").first()
    services.roll_back(first)
    assert Override.objects.get(asset=btc, field="h1").value == "First"
    assert Revision.objects.filter(asset=btc, field="h1").count() == 3


def test_headings_do_not_repeat_the_code(seeded):
    for code, heading in (("BMW", "2030"), ("WTI", "2030"), ("EURUSD", "2030"), ("SHIB", "(SHIB)")):
        asset = Asset.objects.select_related("asset_class").get(code=code)
        add_forecast(asset)
        built = page.build_page(Asset.objects.select_related("asset_class").get(code=code))
        assert built["h1"].endswith(heading)


def test_seed_refresh_replaces_defaults_on_request(btc):
    services.save_template(btc.asset_class, english(), "h1", "Edited")
    call_command("seed_templates", "--refresh", verbosity=0)
    assert Template.objects.get(asset_class=btc.asset_class, language=english(), field="h1").body != "Edited"


def test_seed_keeps_admin_edits(btc):
    services.save_template(btc.asset_class, english(), "h1", "Edited")
    call_command("seed_templates", verbosity=0)
    assert Template.objects.get(asset_class=btc.asset_class, language=english(), field="h1").body == "Edited"


def test_small_site_text_is_imported_and_renders(seeded):
    call_command("import_smallsite_content", verbosity=0)
    silver = Asset.objects.select_related("asset_class").get(code="XAG")
    add_forecast(silver)
    built = page.build_page(Asset.objects.select_related("asset_class").get(code="XAG"))
    assert built["title"].startswith("Silver Price Prediction")
    assert built["drivers"][0]["title"] == "Industrial demand"
    assert built["sources"]["drivers"] == "override"
    before = Override.objects.count()
    call_command("import_smallsite_content", verbosity=0)
    assert Override.objects.count() == before


def test_csv_round_trip(btc):
    services.save_override(btc, english(), "h1", 'With "quotes", commas\nand lines')
    text = csvio.export_overrides()
    Override.objects.all().delete()
    report = csvio.import_overrides(text)
    assert report.saved == 1 and not report.errors
    assert Override.objects.get(field="h1").value == 'With "quotes", commas\nand lines'


def test_csv_import_checks_like_a_manual_save(btc):
    text = "asset,language,field,value\nBTC,en,h1,{nope}\nBTC,en,h_ta,Fine\nZZZ,en,h1,x\n"
    report = csvio.import_overrides(text)
    assert report.saved == 1
    assert len(report.errors) == 2
    assert "line 2" in report.errors[0]


def test_csv_rejects_wrong_columns(btc):
    assert csvio.import_overrides("a,b\n1,2\n").errors == ["expected the columns asset, language, field, value"]


def test_template_csv_round_trip(btc):
    text = csvio.export_templates()
    assert csvio.import_templates(text).saved == Template.objects.count()


class FakeClient:
    def __init__(self, stop_reason="end_turn"):
        self.calls = []
        copy = drafts.AssetCopy(
            drivers=[drafts.Driver(title="Halving", text="Supply  growth\nslows.")],
            bull=["More use."],
            bear=["Less use."],
            risks=["Custody."],
        )
        response = SimpleNamespace(stop_reason=stop_reason, parsed_output=copy)
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=lambda **kw: self.calls.append(kw) or response))


def test_draft_stays_hidden_until_approved(btc):
    drafts.draft_asset(btc, "en", FakeClient())
    assert Draft.objects.filter(asset=btc).count() == 4
    built = page.build_page(btc)
    assert "Halving" not in flat(built)
    assert built["sources"]["drivers"] == "template"

    services.approve_draft(Draft.objects.get(asset=btc, field="drivers"))
    built = page.build_page(btc)
    assert built["drivers"] == [{"title": "Halving", "text": "Supply growth slows."}]
    assert not Draft.objects.filter(asset=btc, field="drivers").exists()
    assert Revision.objects.filter(field="drivers", note__startswith="AI draft").exists()


def test_new_draft_does_not_replace_published_text(btc):
    services.save_override(btc, english(), "bull", "Reviewed text.")
    drafts.draft_asset(btc, "en", FakeClient())
    assert page.build_page(btc)["bull"] == ["Reviewed text."]


def test_draft_request_is_built_from_the_asset(btc):
    client = FakeClient()
    drafts.draft_asset(btc, "en", client)
    call = client.calls[0]
    assert call["model"] == drafts.MODEL
    assert call["output_format"] is drafts.AssetCopy
    assert "Bitcoin" in call["messages"][0]["content"]


def test_refused_draft_saves_nothing(btc):
    with pytest.raises(drafts.DraftFailed):
        drafts.draft_asset(btc, "en", FakeClient(stop_reason="refusal"))
    assert not Draft.objects.exists()


def test_drafting_without_a_key_explains_itself(btc, settings):
    settings.ANTHROPIC_API_KEY = ""
    with pytest.raises(drafts.DraftFailed, match="ANTHROPIC_API_KEY"):
        drafts.request_copy(btc, "en")


def test_figures_in_a_draft_are_flagged():
    assert drafts.has_digits("Around 50 percent")
    assert not drafts.has_digits("Around half")


def test_ai_text_cannot_break_the_template_language():
    assert drafts.clean("A {price} :: B\n\nC") == "A (price): B C"


@pytest.fixture
def admin_client_logged_in(client, db, btc):
    user = get_user_model().objects.create_superuser("root", "r@example.com", "a-long-test-password")
    client.force_login(user)
    return client


def test_every_admin_list_opens(admin_client_logged_in):
    for model, model_admin in site._registry.items():
        info = model._meta.app_label, model._meta.model_name
        response = admin_client_logged_in.get(reverse(f"admin:{info[0]}_{info[1]}_changelist"))
        assert response.status_code == 200, model_admin


def test_admin_rejects_an_unknown_substitution(admin_client_logged_in, btc):
    url = reverse("admin:content_override_add")
    data = {"asset": btc.pk, "language": english().pk, "field": "h1", "value": "{nope}"}
    response = admin_client_logged_in.post(url, data)
    assert response.status_code == 200
    assert b"unknown substitution" in response.content
    assert not Override.objects.exists()


def test_admin_save_lands_in_the_history(admin_client_logged_in, btc):
    url = reverse("admin:content_override_add")
    data = {"asset": btc.pk, "language": english().pk, "field": "h1", "value": "Mine"}
    assert admin_client_logged_in.post(url, data).status_code == 302
    assert Override.objects.get(field="h1").value == "Mine"
    assert Revision.objects.filter(field="h1", user__username="root").exists()


def test_csv_pages_open(admin_client_logged_in):
    assert admin_client_logged_in.get(reverse("admin:templates_export")).status_code == 200
    assert admin_client_logged_in.get(reverse("admin:templates_import")).status_code == 200


def test_accuracy_csv_export(admin_client_logged_in):
    url = reverse("admin:forecasts_forecastaccuracy_changelist")
    rows = list(ForecastAccuracy.objects.values_list("pk", flat=True))
    response = admin_client_logged_in.post(url, {"action": "export_csv", "_selected_action": rows})
    assert response.status_code == 200
    assert b"BTC" in response.content


def test_asset_classes_are_seeded_for_every_template(seeded):
    assert Template.objects.values("asset_class").distinct().count() == AssetClass.objects.count()
