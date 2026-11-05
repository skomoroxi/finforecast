from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("core", "0001_timescaledb"), ("market", "0001_initial")]

    operations = [
        migrations.RunSQL(
            "SELECT create_hypertable('market_pricebar', 'date',"
            " chunk_time_interval => INTERVAL '1 year', migrate_data => true);",
            migrations.RunSQL.noop,
        )
    ]
