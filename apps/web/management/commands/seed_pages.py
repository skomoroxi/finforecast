from django.core.management.base import BaseCommand

from apps.content.models import Comparison, Language, Page, Reviewer
from apps.market.models import Asset

COMPARISONS = [("BTC", "ETH"), ("XAU", "XAG"), ("WTI", "BRENT"), ("NVDA", "AMD"), ("AAPL", "MSFT"), ("BMW", "MBG")]

METHODOLOGY = """
<h2>Data</h2>
<p>Daily prices come from public market data providers and are updated after each close. For each day we store
the open, close and an average price, plus the high and low where the source has them. Some values are estimates,
and the pages say so:</p>
<ul>
  <li>Silver: the close is real, the day's high and low are estimated from a silver ETF.</li>
  <li>German shares: older prices are estimated in euros from the US-traded ADR and the EUR/USD rate. Recent days use
  real XETRA closes where available.</li>
  <li>Indices: forecasts are built on an exchange-traded fund that tracks the index, not on index points.</li>
</ul>

<h2>The three forecasting models</h2>
<p><strong>ARIMA</strong> describes short-term price behaviour on the last five years of data. The model order, and
whether to include a drift, are chosen by the lowest AIC.</p>
<p><strong>Trend + mean reversion</strong> fits a long-run trend and how far the price moves around it. When the price
is far from the trend, the forecast gradually pulls it back.</p>
<p><strong>Monte Carlo</strong> simulates 10,000 possible price paths from the long-run average daily return and recent
volatility. The forecast is the median path, and the range covers 80% of paths.</p>
<p>The <strong>consensus</strong> is the average of the three. ARIMA is left out beyond 2030, where it adds no
information.</p>

<h2>Long-run growth cap</h2>
<p>No path may grow or fall faster than 25% a year on average. Without the cap, a young asset's short history would
produce extreme long-term numbers. The cap is a modelling choice, not a prediction.</p>

<h2>Accuracy</h2>
<p>Every published forecast is stored and compared with the real price when its date arrives. Until there are 30 such
comparisons, pages show a walk-forward test, where the models are refit at past dates on the data available then.
See the <a href="/accuracy/">accuracy page</a>.</p>

<h2>Technical analysis</h2>
<p>12 indicators, 12 moving averages and 5 sets of pivot points are calculated for daily, weekly and monthly bars. The
summary counts buy, sell and neutral signals. Assets with closing prices only show the indicators a close can
support.</p>

<h2>Limitations</h2>
<p>Models learn only from past prices and cannot anticipate news or events. Their ability to call the direction of the
next move is close to chance, so the ranges matter more than any single value.</p>
"""

ABOUT = """
<p>FinForecast publishes daily statistical price forecasts for cryptocurrencies, stocks, metals, energy and currency
pairs, together with technical analysis and measured accuracy. The site is educational: it explains what statistical
models say and how reliable they have been.</p>
<h2>Data</h2>
<p>Market data comes from Twelve Data, Alpha Vantage, Binance, Kraken, Finnhub and FRED.</p>
<p>Nothing on this site is investment advice. See the <a href="/disclaimer/">disclaimer</a>.</p>
"""

DISCLAIMER = """
<h2>Not investment advice</h2>
<p>The forecasts, technical analysis and other content on FinForecast are produced by statistical models for general
information only. They are not investment, financial, tax or legal advice, and they are not a recommendation to buy,
sell or hold any asset.</p>
<h2>Forecasts can be wrong</h2>
<p>Models are based on past prices and cannot anticipate future events. Actual prices can differ substantially from any
forecast or range shown. Past performance does not guarantee future results. The measured accuracy of the models is
published on the <a href="/accuracy/">accuracy page</a>.</p>
<h2>Your responsibility</h2>
<p>Investing involves risk, including the loss of your capital. Consider your own circumstances and, where appropriate,
consult a licensed financial adviser before making investment decisions.</p>
<h2>Data</h2>
<p>Market data is supplied by third parties and may contain errors or delays. Some values are estimates, as explained
in the <a href="/methodology/">methodology</a>.</p>
"""

PAGES = [
    ("methodology", "Methodology", "How the forecasts are made, and what they cannot do.", METHODOLOGY),
    ("about", "About FinForecast", "", ABOUT),
    ("disclaimer", "Disclaimer", "", DISCLAIMER),
    ("privacy", "Privacy", "", "<p>The full privacy policy is being prepared.</p>"),
    ("contact", "Contact", "", "<p>Contact details will be added before launch.</p>"),
]


class Command(BaseCommand):
    help = "Add the standard pages and comparisons. Existing ones keep their admin edits."

    def handle(self, *args, **options):
        english = Language.objects.get(code="en")
        reviewer = Reviewer.objects.filter(slug="margerie-holtz").first()
        added = 0
        for slug, title, summary, body in PAGES:
            _, created = Page.objects.get_or_create(
                kind=Page.Kind.STATIC,
                slug=slug,
                language=english,
                defaults={
                    "title": title,
                    "summary": summary,
                    "body": body.strip(),
                    "published": True,
                    "reviewer": reviewer if slug == "methodology" else None,
                },
            )
            added += created
        assets = {a.code: a for a in Asset.objects.all()}
        for left, right in COMPARISONS:
            if right == "BRENT":
                continue  # Brent is a supporting series, it has no forecast of its own
            slug = f"{assets[left].slug.split('-')[0]}-vs-{assets[right].slug.split('-')[0]}"
            Comparison.objects.get_or_create(slug=slug, defaults={"left": assets[left], "right": assets[right]})
        self.stdout.write(f"{added} pages added")
