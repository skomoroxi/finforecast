"""The editor, reviewers, blocks, analysts and job log."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from apps.content import csvio, page, services
from apps.content.models import AnalystTarget, CustomBlock, Draft, Language, Override, Reviewer
from apps.market.models import Asset, FetchResult, FetchRun

from .test_page import add_forecast


@pytest.fixture
def seeded(db):
    call_command("seed_assets", verbosity=0)
    call_command("seed_templates", verbosity=0)


@pytest.fixture
def btc(seeded):
    asset = Asset.objects.select_related("asset_class").get(code="BTC")
    add_forecast(asset)
    return Asset.objects.select_related("asset_class").get(code="BTC")


@pytest.fixture
def staff(client, btc):
    user = get_user_model().objects.create_superuser("root", "r@example.com", "a-long-test-password")
    client.force_login(user)
    return client


def english():
    return Language.objects.get(code="en")


def url(code="BTC", lang="en"):
    return reverse("admin:content_editor", args=[code, lang])


def test_editor_shows_state_and_todays_text(staff, btc):
    services.save_override(btc, english(), "h1", "Mine at {price}")
    html = staff.get(url()).content.decode()
    assert "Your value" in html and "Template" in html
    assert "Mine at $100" in html


def test_editor_save_and_reset(staff, btc):
    assert staff.post(url(), {"field": "h1", "value": "Mine", "action": "save"}).status_code == 302
    assert Override.objects.get(asset=btc, field="h1").value == "Mine"
    staff.post(url(), {"field": "h1", "action": "reset"})
    assert not Override.objects.filter(asset=btc, field="h1").exists()


def test_editor_refuses_an_unknown_substitution(staff, btc):
    response = staff.post(url(), {"field": "h1", "value": "{nope}", "action": "save"}, follow=True)
    html = response.content.decode()
    assert "unknown substitution" in html
    assert not Override.objects.exists()
    assert "{nope}" in html  # the person keeps what they typed


def test_editor_warns_on_a_long_title_but_saves(staff, btc):
    response = staff.post(url(), {"field": "title", "value": "x" * 80, "action": "save"}, follow=True)
    assert "the limit is 60" in response.content.decode()
    assert Override.objects.filter(field="title").exists()


def test_german_tab_opens_without_templates(staff):
    html = staff.get(url(lang="de")).content.decode()
    assert "No text" in html


def test_editor_approves_and_discards_drafts(staff, btc):
    Draft.objects.create(asset=btc, language=english(), field="bull", value="Good 50.", model_name="m")
    Draft.objects.create(asset=btc, language=english(), field="bear", value="Bad.", model_name="m")
    html = staff.get(url()).content.decode()
    assert "AI draft, not published" in html and "contains a figure" in html
    staff.post(url(), {"field": "bull", "action": "approve"})
    staff.post(url(), {"field": "bear", "action": "reject"})
    assert Override.objects.get(asset=btc, field="bull").value == "Good 50."
    assert not Draft.objects.exists()
    assert not Override.objects.filter(field="bear").exists()


def test_asset_list_links_to_the_editor(staff):
    assert url() in staff.get(reverse("admin:market_asset_changelist")).content.decode()


def test_reviewer_default_and_choice(btc):
    assert page.build_page(btc)["reviewer"]["name"] == "Margerie Holtz"
    other = Reviewer.objects.create(slug="sam", name="Sam Lee", job_title="Analyst")
    services.save_override(btc, english(), "reviewer", other.name)
    assert page.build_page(btc)["reviewer"]["slug"] == "sam"


def test_unknown_reviewer_is_refused(btc):
    report = csvio.import_overrides("asset,language,field,value\nBTC,en,reviewer,Nobody\n")
    assert report.errors and report.saved == 0


def test_custom_block_renders_with_variables_in_its_place(btc):
    CustomBlock.objects.create(
        asset=btc, language=english(), after_section="ta", title="Note on {code}", body="Price {price}."
    )
    CustomBlock.objects.create(asset=btc, language=english(), after_section="ta", title="Off", body="x", enabled=False)
    blocks = page.build_page(btc)["blocks"]
    assert len(blocks) == 1
    assert blocks[0]["after"] == "ta" and blocks[0]["title"] == "Note on BTC"
    assert blocks[0]["paragraphs"][0].startswith("Price $100")


def test_custom_block_with_a_bad_variable_is_refused(staff, btc):
    data = {
        "asset": btc.pk,
        "language": english().pk,
        "after_section": "ta",
        "title": "T",
        "body": "{nope}",
        "order": 0,
        "enabled": "on",
    }
    response = staff.post(reverse("admin:content_customblock_add"), data)
    assert b"unknown substitution" in response.content
    assert not CustomBlock.objects.exists()


def analyst(asset, **kw):
    fields = {
        "asset": asset,
        "institution": "Example Bank",
        "kind": "bank",
        "target": 120,
        "basis": "end",
        "horizon": "2027",
        "published_on": date(2026, 10, 1),
        "source_title": "Outlook",
        "source_url": "https://example.com/outlook",
    }
    return AnalystTarget(**(fields | kw))


def test_analyst_needs_a_target_or_a_range(btc):
    analyst(btc).full_clean()
    analyst(btc, target=None, target_low=100, target_high=140).full_clean()
    with pytest.raises(ValidationError):
        analyst(btc, target=None).full_clean()
    with pytest.raises(ValidationError):
        analyst(btc, target_low=100, target_high=140).full_clean()
    with pytest.raises(ValidationError):
        analyst(btc, target=None, target_low=140, target_high=100).full_clean()


def test_analyst_needs_a_real_source(btc):
    with pytest.raises(ValidationError):
        analyst(btc, source_url="http://example.com").full_clean()
    with pytest.raises(ValidationError):
        analyst(btc, horizon="next year").full_clean()


def test_hidden_analyst_stays_off_the_page(btc):
    analyst(btc).save()
    analyst(btc, institution="Hidden", show=False).save()
    assert [a["institution"] for a in page.build_page(btc)["analysts"]] == ["Example Bank"]


def test_rerun_failed_assets_queues_only_those(staff, btc, monkeypatch):
    queued = []
    monkeypatch.setattr("apps.market.admin.rerun", lambda task, codes: queued.append((task, codes)))
    run = FetchRun.objects.create(task="update:crypto")
    FetchResult.objects.create(run=run, asset=btc, ok=False, message="down")
    eth = Asset.objects.get(code="ETH")
    FetchResult.objects.create(run=run, asset=eth, ok=True)
    changelist = reverse("admin:market_fetchrun_changelist")
    staff.post(changelist, {"action": "rerun_failed", "_selected_action": [run.pk]})
    assert queued == [("update:crypto", ["BTC"])]


def test_dashboard_shows_what_needs_attention(staff, btc):
    run = FetchRun.objects.create(task="update:crypto")
    FetchResult.objects.create(run=run, asset=btc, ok=False, message="feed down")
    html = staff.get(reverse("admin:index")).content.decode()
    assert "feed down" in html and "failures in 24 hours" in html


def test_admin_opens_with_a_password_alone(client, db):
    user = get_user_model().objects.create_superuser("root", "r@example.com", "a-long-test-password")
    assert client.login(username="root", password="a-long-test-password")
    assert client.get(reverse("admin:index")).status_code == 200
    assert user.is_staff
