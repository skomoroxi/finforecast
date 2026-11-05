from django.core.management.base import BaseCommand

from apps.content import defaults, services
from apps.content.models import Language, Template
from apps.market.models import AssetClass

LANGUAGES = [("en", "English", True, "us"), ("de", "Deutsch", False, "de")]


class Command(BaseCommand):
    help = "Add missing default templates. Existing ones keep their admin edits."

    def handle(self, *args, **options):
        for code, name, enabled, country in LANGUAGES:
            Language.objects.get_or_create(code=code, defaults={"name": name, "enabled": enabled, "country": country})
        english = Language.objects.get(code="en")

        added = 0
        for asset_class in AssetClass.objects.all():
            present = set(
                Template.objects.filter(asset_class=asset_class, language=english).values_list("field", flat=True)
            )
            for field, body in defaults.templates_for(asset_class.code).items():
                if field not in present:
                    services.save_template(asset_class, english, field, body, note="default")
                    added += 1
        self.stdout.write(f"{added} templates added")
