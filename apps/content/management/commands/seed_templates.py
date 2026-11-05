from django.core.management.base import BaseCommand

from apps.content import defaults, services
from apps.content.models import Language, Reviewer, ReviewerBio, Template
from apps.market.models import AssetClass

BIO = (
    "Margerie Holtz is a Senior Analyst with more than eight years of experience in financial markets. "
    "She has worked at Brown Brothers Harriman since 2017 and has been a Senior Analyst there since 2020. "
    "She holds a Master of Arts in International Economics from the Hochschule für Wirtschaft und Recht "
    "Berlin (2015). At FinForecast she reviews the forecasting methodology and the analyst-forecast data."
)
LANGUAGES = [("en", "English", True, "us"), ("de", "Deutsch", False, "de")]


class Command(BaseCommand):
    help = "Add missing default templates. Existing ones keep their admin edits unless --refresh is given."

    def add_arguments(self, parser):
        parser.add_argument("--refresh", action="store_true", help="Overwrite existing templates with the defaults.")

    def handle(self, *args, refresh=False, **options):
        for code, name, enabled, country in LANGUAGES:
            Language.objects.get_or_create(code=code, defaults={"name": name, "enabled": enabled, "country": country})
        english = Language.objects.get(code="en")

        reviewer, _ = Reviewer.objects.get_or_create(
            slug="margerie-holtz", defaults={"name": "Margerie Holtz", "job_title": "Senior Analyst"}
        )
        ReviewerBio.objects.get_or_create(reviewer=reviewer, language=english, defaults={"bio": BIO})

        added = 0
        for asset_class in AssetClass.objects.all():
            rows = Template.objects.filter(asset_class=asset_class, language=english)
            present = dict(rows.values_list("field", "body"))
            for field, body in defaults.templates_for(asset_class.code).items():
                current = present.get(field)
                if current is None or (refresh and current != body):
                    services.save_template(asset_class, english, field, body, note="default")
                    added += 1
        self.stdout.write(f"{added} templates written")
