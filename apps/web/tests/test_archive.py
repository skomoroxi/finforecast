import re

from apps.web import archive


def test_bitcoin_archive_opens_frozen_and_unindexed(client):
    response = client.get("/bitcoin-price-prediction-old/")
    assert response.status_code == 200
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    body = response.content.decode()
    assert "Archived copy of" in body
    assert '<meta name="robots" content="noindex, nofollow">' in body
    assert '<link rel="canonical" href="https://price-predictions.net/bitcoin-price-prediction/">' in body
    assert "{{static:" not in body
    assert "/static/web/archive/2026-11-12/site.css" in body


def test_archive_assets_exist():
    static_root = archive.FOLDER.parent / "static"
    for slug in archive.PAGES:
        raw = (archive.FOLDER / archive.PAGES[slug]).read_text(encoding="utf-8")
        for path in re.findall(r"\{\{static:([^}]+)\}\}", raw):
            assert (static_root / path).is_file(), path


def test_unknown_archive_is_404(rf):
    from django.http import Http404

    from apps.web.views import archived_page

    try:
        archived_page(rf.get("/x/"), "nope")
    except Http404:
        return
    raise AssertionError("expected 404")
