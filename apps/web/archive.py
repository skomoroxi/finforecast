"""Frozen copies of pages as they stood before a content change, kept for before/after comparison.

Each copy is the rendered HTML saved on the day, with its CSS, scripts, fonts and images copied into
``static/web/archive/<date>/`` so later style changes cannot alter it. ``{{static:<path>}}`` tokens in the
HTML are resolved through the static storage, so the copy works with hashed file names too.
Archive pages are never indexed, whatever ``INDEXING`` says.
"""

import re
from functools import cache
from pathlib import Path

from django.templatetags.static import static

FOLDER = Path(__file__).resolve().parent / "archive_pages"

# URL slug -> saved HTML file in FOLDER
PAGES = {
    "bitcoin-price-prediction-old": "bitcoin-price-prediction-2026-11-12.html",
}

TOKEN = re.compile(r"\{\{static:([^}]+)\}\}")


@cache
def html(slug: str) -> str:
    text = (FOLDER / PAGES[slug]).read_text(encoding="utf-8")
    return TOKEN.sub(lambda m: static(m.group(1)), text)
