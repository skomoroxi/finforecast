"""Bring the small site's archived forecasts in, so its head start counts towards live accuracy."""

import json
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.forecasts.models import ForecastPoint, ForecastRun
from apps.market.models import Asset

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "smallsite.json"
CODES = {
    "silver": "XAG",
    "gold": "XAU",
    "bitcoin": "BTC",
    "xrp": "XRP",
    "solana": "SOL",
    "dogecoin": "DOGE",
    "nvidia": "NVDA",
    "amazon": "AMZN",
}
METHODS = ("arima", "reversion", "montecarlo", "consensus")


class Command(BaseCommand):
    help = "Import smallsite.json. Safe to repeat: runs already stored are skipped."

    def handle(self, *args, **options):
        added = 0
        for entry in json.loads(FIXTURE.read_text(encoding="utf-8")):
            asset = Asset.objects.get(code=CODES[entry["asset"]])
            run_date = date.fromisoformat(entry["run_date"])
            if ForecastRun.objects.filter(asset=asset, run_date=run_date).exists():
                continue
            run = ForecastRun.objects.create(
                asset=asset,
                run_date=run_date,
                data_date=date.fromisoformat(entry["last_close"]["date"]),
                last_close=entry["last_close"]["price"],
                model_version="small-site",
            )
            points = []
            for row in entry["daily"]:
                for method in METHODS:
                    if row.get(method) is None:
                        continue
                    band = {"p10": row.get("low"), "p90": row.get("high")} if method == "consensus" else {}
                    points.append(
                        ForecastPoint(
                            run_date=run_date,
                            run=run,
                            asset=asset,
                            method=method,
                            horizon="daily",
                            target=date.fromisoformat(row["date"]),
                            value=row[method],
                            **band,
                        )
                    )
            ForecastPoint.objects.bulk_create(points)
            added += 1
        self.stdout.write(f"{added} small-site runs imported")
