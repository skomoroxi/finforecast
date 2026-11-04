"""Enable TimescaleDB: price and forecast tables become hypertables in later milestones."""

from django.db import migrations


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.RunSQL("CREATE EXTENSION IF NOT EXISTS timescaledb;", reverse_sql=migrations.RunSQL.noop),
    ]
