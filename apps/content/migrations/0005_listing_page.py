import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0004_comparison_content"),
        ("market", "0004_asset_country_asset_slug"),
    ]

    operations = [
        migrations.CreateModel(
            name="ListingPage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=True)),
                (
                    "title",
                    models.CharField(blank=True, help_text="Title tag. Empty = default pattern.", max_length=200),
                ),
                ("meta_description", models.CharField(blank=True, help_text="Empty = default pattern.", max_length=300)),
                ("h1", models.CharField(blank=True, help_text="Empty = default pattern.", max_length=200)),
                ("intro", models.TextField(blank=True, help_text="Paragraphs in the hero.")),
                (
                    "body",
                    models.TextField(
                        blank=True,
                        help_text="Paragraphs after the chart; a paragraph starting with '## ' is a heading.",
                    ),
                ),
                ("faq", models.TextField(blank=True, help_text="Question :: answer, one pair per paragraph.")),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="listing_pages", to="market.asset"
                    ),
                ),
                (
                    "language",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="listing_pages",
                        to="content.language",
                    ),
                ),
            ],
            options={
                "constraints": [models.UniqueConstraint(fields=("asset", "language"), name="listing_page_unique")],
            },
        ),
    ]
