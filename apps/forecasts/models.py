"""Stored forecasts, their accuracy and the technical analysis snapshot (TECHNICAL-TASK §4, §6.3, §11).

Forecasts are kept forever: comparing methods with each other and with real prices is the point.
"""

from django.db import models

from apps.market.models import Asset


class Method(models.TextChoices):
    ARIMA = "arima", "ARIMA"
    REVERSION = "reversion", "Trend + mean reversion"
    MONTECARLO = "montecarlo", "Monte Carlo"
    CONSENSUS = "consensus", "Consensus"


class Horizon(models.TextChoices):
    DAILY = "daily", "Daily"
    MONTHLY = "monthly", "Monthly"
    YEARLY = "yearly", "Yearly"


class ForecastRun(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="forecast_runs")
    run_date = models.DateField()
    data_date = models.DateField(help_text="Date of the last close the run saw.")
    last_close = models.FloatField()
    model_version = models.CharField(max_length=20)
    methods = models.JSONField(default=dict, help_text="Status and parameters of each method.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-run_date", "asset_id"]
        constraints = [models.UniqueConstraint(fields=["asset", "run_date"], name="one_run_per_asset_per_day")]

    def __str__(self):
        return f"{self.asset} {self.run_date}"


class ForecastPoint(models.Model):
    """One forecast value. A compressed TimescaleDB hypertable partitioned on `run_date`.

    Daily: the value for that date. Monthly: the month average, with `target` on the 1st and the band
    the month's lowest P10 and highest P90. Yearly: the year average, with `target` on 1 January.
    """

    pk = models.CompositePrimaryKey("run_date", "run_id", "method", "horizon", "target")
    run_date = models.DateField()
    run = models.ForeignKey(ForecastRun, on_delete=models.CASCADE, related_name="points")
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="+")
    method = models.CharField(max_length=12, choices=Method.choices)
    horizon = models.CharField(max_length=8, choices=Horizon.choices)
    target = models.DateField()
    value = models.FloatField()
    p10 = models.FloatField(null=True)
    p90 = models.FloatField(null=True)

    class Meta:
        ordering = ["run_date", "run_id", "method", "horizon", "target"]

    def __str__(self):
        return f"{self.asset_id} {self.method} {self.target}: {self.value}"


class ForecastAccuracy(models.Model):
    class Basis(models.TextChoices):
        LIVE = "live", "Stored forecasts vs real prices"
        BACKTEST = "backtest", "Walk-forward backtest"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="accuracy")
    method = models.CharField(max_length=12, choices=Method.choices)
    horizon = models.CharField(max_length=6, help_text="1d, 7d, 30d or month.")
    window_days = models.PositiveIntegerField(default=0, help_text="30, 90 or 365; 0 for a backtest.")
    basis = models.CharField(max_length=10, choices=Basis.choices)
    mape = models.FloatField()
    mae = models.FloatField()
    direction_pct = models.FloatField(null=True, help_text="How often the rise or fall was called right.")
    in_range_pct = models.FloatField(null=True, help_text="How often the real price landed inside P10-P90.")
    bias_pct = models.FloatField(null=True, help_text="Above zero: forecasts ran too high on average.")
    samples = models.PositiveIntegerField()
    computed_on = models.DateField()

    class Meta:
        verbose_name_plural = "forecast accuracy"
        ordering = ["asset_id", "method", "horizon", "window_days"]
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "method", "horizon", "window_days", "basis"], name="one_accuracy_row_per_slice"
            )
        ]

    def __str__(self):
        return f"{self.asset} {self.method} {self.horizon}: {self.mape:.2f}%"


class TechnicalSnapshot(models.Model):
    """The latest technical analysis of one asset: oscillators, moving averages and pivots per timeframe."""

    asset = models.OneToOneField(Asset, on_delete=models.CASCADE, related_name="technicals")
    run_date = models.DateField()
    ohlc_basis = models.CharField(max_length=10, help_text="full, proxy, estimate or close.")
    timeframes = models.JSONField()

    def __str__(self):
        return f"{self.asset} {self.run_date}"
