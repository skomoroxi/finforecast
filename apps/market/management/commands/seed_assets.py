from django.core.management.base import BaseCommand

from apps.market import catalog
from apps.market.models import AdrConversion, Asset, AssetClass


class Command(BaseCommand):
    help = "Add catalog assets that are missing. Existing rows keep their admin edits unless --refresh is given."

    def add_arguments(self, parser):
        parser.add_argument("--refresh", action="store_true", help="Overwrite existing rows with catalog values.")

    def handle(self, *args, refresh=False, **options):
        classes = {}
        for code, name, calendar, unit, max_change in catalog.CLASSES:
            classes[code], _ = AssetClass.objects.get_or_create(
                code=code,
                defaults={"name": name, "calendar": calendar, "default_unit": unit, "max_daily_change": max_change},
            )

        rows = catalog.asset_rows()
        created = 0
        for row in rows:
            fields = {k: v for k, v in row.items() if k not in ("code", "series_of", "proxy")}
            asset_class = classes[fields.pop("asset_class")]
            fields["asset_class"] = asset_class
            fields.setdefault("unit", asset_class.default_unit)
            if refresh:
                _, was_created = Asset.objects.update_or_create(code=row["code"], defaults=fields)
            else:
                _, was_created = Asset.objects.get_or_create(code=row["code"], defaults=fields)
            created += was_created

        by_code = {a.code: a for a in Asset.objects.all()}
        for row in rows:  # rows from before these fields existed
            asset = by_code[row["code"]]
            if not asset.slug:
                Asset.objects.filter(pk=asset.pk).update(slug=row["slug"], country=row["country"])
        for row in rows:
            asset = by_code[row["code"]]
            parent = by_code.get(row.get("series_of"))
            proxy = by_code.get(row.get("proxy"))
            if asset.series_of != parent or asset.proxy != proxy:
                Asset.objects.filter(pk=asset.pk).update(series_of=parent, proxy=proxy)

        for code, _name, adr, xetra in catalog.STOCKS_GERMAN:
            AdrConversion.objects.get_or_create(
                asset=by_code[code], defaults={"adr_asset": by_code[adr], "xetra_symbol": xetra}
            )

        self.stdout.write(f"{created} assets added, {len(rows)} in the catalog")
