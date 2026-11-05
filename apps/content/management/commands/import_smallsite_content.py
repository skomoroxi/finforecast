"""The small site's hand-written text for its 8 assets becomes manual values on the big site."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.content import services
from apps.content.models import Language, Override
from apps.forecasts.management.commands.import_smallsite import CODES
from apps.market.models import Asset

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "smallsite_content.json"
HEADINGS = {
    "summary": "h_summary",
    "chart": "h_chart",
    "next30": "h_next30",
    "tomorrow": "h_tomorrow",
    "thisYear": "h_this_year",
    "fiveYears": "h_five_years",
    "outlook": "h_outlook",
    "ta": "h_ta",
    "analysts": "h_analysts",
    "drivers": "h_drivers",
    "history": "h_history",
    "investment": "h_investment",
    "accuracy": "h_accuracy",
}


def variables(text: str) -> str:
    return text.replace("{Y}", "{year}").replace("{L}", "{last_year}")


def fields_of(entry: dict) -> dict[str, str]:
    out = {}
    for key in ("title", "h1", "intro"):
        if entry.get(key):
            out[key] = variables(entry[key])
    for key, value in (entry.get("h") or {}).items():
        if key in HEADINGS:
            out[HEADINGS[key]] = variables(value)
    if entry.get("drivers"):
        out["drivers"] = "\n\n".join(f"{d['title']} :: {d['text']}" for d in entry["drivers"])
    for key in ("bull", "bear", "risks"):
        if entry.get(key):
            out[key] = "\n\n".join(entry[key])
    return out


class Command(BaseCommand):
    help = "Import smallsite_content.json. Fields already edited are left alone."

    def handle(self, *args, **options):
        english = Language.objects.get(code="en")
        added = 0
        for slug, entry in json.loads(FIXTURE.read_text(encoding="utf-8")).items():
            asset = Asset.objects.get(code=CODES[slug])
            for field, value in fields_of(entry).items():
                if not Override.objects.filter(asset=asset, language=english, field=field).exists():
                    services.save_override(asset, english, field, value, note="small site")
                    added += 1
        self.stdout.write(f"{added} manual values imported")
