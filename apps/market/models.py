"""Assets, daily prices and the fetch log (TECHNICAL-TASK §3, §6.1, §6.2, §13)."""

from django.db import models


class Calendar(models.TextChoices):
    CRYPTO = "crypto", "7 days"
    NYSE = "nyse", "Mon-Fri, stock exchange"
    FX = "fx", "Mon-Fri, FX day"


class Source(models.TextChoices):
    TWELVEDATA = "twelvedata", "Twelve Data"
    BINANCE = "binance", "Binance"
    ALPHAVANTAGE = "alphavantage", "Alpha Vantage"
    FRED = "fred", "FRED"
    KRAKEN = "kraken", "Kraken"
    ADR = "adr", "Calculated from ADR"


class Basis(models.TextChoices):
    FULL = "full", "Open, high, low, close"
    CLOSE = "close", "Close only"
    PROXY = "proxy", "Close; range estimated from a tracking instrument"
    ESTIMATE = "estimate", "Estimated from ADR"


class AssetClass(models.Model):
    code = models.SlugField(max_length=20, unique=True)
    name = models.CharField(max_length=60)
    calendar = models.CharField(max_length=10, choices=Calendar.choices)
    default_unit = models.CharField(max_length=30, blank=True)
    max_daily_change = models.FloatField(help_text="A bigger close-to-close move rejects the bar for a manual check.")
    max_annual_drift = models.FloatField(default=0.25, help_text="Forecast growth cap per year.")

    class Meta:
        verbose_name_plural = "asset classes"
        ordering = ["code"]

    def __str__(self):
        return self.name


class Asset(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, blank=True, help_text="Address of the English page.")
    country = models.CharField(max_length=10, blank=True, help_text="Listing: us, de or asia.")
    asset_class = models.ForeignKey(AssetClass, on_delete=models.PROTECT, related_name="assets")
    currency = models.CharField(max_length=3, default="USD")
    unit = models.CharField(max_length=30, blank=True)
    enabled = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=1000)
    color = models.CharField(max_length=7, blank=True, help_text="Chart colour, #rrggbb.")

    source = models.CharField(max_length=20, choices=Source.choices)
    symbol = models.CharField(max_length=30, blank=True)
    fallback_source = models.CharField(max_length=20, choices=Source.choices, blank=True)
    fallback_symbol = models.CharField(max_length=30, blank=True)
    history_source = models.CharField(
        max_length=20, choices=Source.choices, blank=True, help_text="Older segment, e.g. FTM before it became Sonic."
    )
    history_symbol = models.CharField(max_length=30, blank=True)
    main_from = models.DateField(
        null=True, blank=True, help_text="Ignore the main source before this date, e.g. an unrelated older token."
    )
    live_symbol = models.CharField(max_length=30, blank=True, help_text="Finnhub symbol for the live price.")

    series_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="series",
        help_text="Set for a supporting series with no page of its own (Brent, an ADR, SLV).",
    )
    proxy = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="proxy_for",
        help_text="Instrument whose daily range estimates this close-only asset's range.",
    )
    max_annual_drift = models.FloatField(null=True, blank=True, help_text="Overrides the class value.")

    class Meta:
        ordering = ["order", "code"]

    def __str__(self):
        return self.code


class AdrConversion(models.Model):
    """How a German share's XETRA euro price is estimated from its US ADR (TECHNICAL-TASK §3.1)."""

    class Status(models.TextChoices):
        OK = "ok", "OK"
        PENDING = "pending", "Waiting for the first ratio"
        PAUSED = "paused", "Paused: ratio jumped, check it"

    asset = models.OneToOneField(Asset, on_delete=models.CASCADE, related_name="adr")
    adr_asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="+")
    xetra_symbol = models.CharField(max_length=20)
    ratio_auto = models.DecimalField(max_digits=16, decimal_places=8, null=True, blank=True)
    ratio_manual = models.DecimalField(
        max_digits=16, decimal_places=8, null=True, blank=True, help_text="When set, it wins over the automatic ratio."
    )
    ratio_candidate = models.DecimalField(
        max_digits=16, decimal_places=8, null=True, blank=True, help_text="Rejected new ratio, waiting for a decision."
    )
    ratio_updated_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    class Meta:
        verbose_name = "ADR conversion"

    def __str__(self):
        return f"{self.asset} from {self.adr_asset}"

    @property
    def ratio(self):
        return self.ratio_manual if self.ratio_manual is not None else self.ratio_auto


class PriceBar(models.Model):
    """One asset, one day. A TimescaleDB hypertable partitioned on `date`."""

    pk = models.CompositePrimaryKey("asset_id", "date")
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="bars")
    date = models.DateField()
    open = models.DecimalField(max_digits=28, decimal_places=12, null=True)
    high = models.DecimalField(max_digits=28, decimal_places=12, null=True)
    low = models.DecimalField(max_digits=28, decimal_places=12, null=True)
    close = models.DecimalField(max_digits=28, decimal_places=12)
    avg = models.DecimalField(max_digits=28, decimal_places=12)
    volume = models.FloatField(null=True)
    source = models.CharField(max_length=20, choices=Source.choices)
    basis = models.CharField(max_length=10, choices=Basis.choices, default=Basis.FULL)

    class Meta:
        ordering = ["asset_id", "date"]

    def __str__(self):
        return f"{self.asset_id} {self.date} {self.close}"


class FetchRun(models.Model):
    task = models.CharField(max_length=40)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    ok_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.task} {self.started_at:%Y-%m-%d %H:%M}"


class FetchResult(models.Model):
    run = models.ForeignKey(FetchRun, on_delete=models.CASCADE, related_name="results")
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="fetch_results")
    ok = models.BooleanField()
    source = models.CharField(max_length=20, blank=True)
    bars = models.PositiveIntegerField(default=0)
    last_date = models.DateField(null=True, blank=True)
    message = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-run_id", "asset_id"]

    def __str__(self):
        return f"{self.asset_id}: {'ok' if self.ok else 'failed'}"
