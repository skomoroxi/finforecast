from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0003_comparison_page"),
    ]

    operations = [
        migrations.AddField(
            model_name="comparison",
            name="title",
            field=models.CharField(blank=True, help_text="Title tag. Empty = default pattern.", max_length=200),
        ),
        migrations.AddField(
            model_name="comparison",
            name="meta_description",
            field=models.CharField(blank=True, help_text="Empty = default pattern.", max_length=300),
        ),
        migrations.AddField(
            model_name="comparison",
            name="intro",
            field=models.TextField(blank=True, help_text="Paragraphs shown above the table."),
        ),
        migrations.AddField(
            model_name="comparison",
            name="faq",
            field=models.TextField(blank=True, help_text="Question :: answer, one pair per paragraph."),
        ),
        migrations.AddField(
            model_name="comparison",
            name="block_title",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="comparison",
            name="block_body",
            field=models.TextField(blank=True, help_text="Paragraphs shown after the table, under block_title."),
        ),
    ]
