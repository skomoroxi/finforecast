from django.db import migrations

# A month to a chunk; chunks older than 30 days are compressed. Runs never write to a date that old.
SQL = """
SELECT create_hypertable('forecasts_forecastpoint', 'run_date', chunk_time_interval => INTERVAL '1 month');
ALTER TABLE forecasts_forecastpoint SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asset_id, method, horizon',
    timescaledb.compress_orderby = 'run_date, run_id, target'
);
SELECT add_compression_policy('forecasts_forecastpoint', INTERVAL '30 days');
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0001_timescaledb"), ("forecasts", "0001_initial")]

    operations = [migrations.RunSQL(SQL, migrations.RunSQL.noop)]
