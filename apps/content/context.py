"""The values a page can use, built from the same rows as its tables (TECHNICAL-TASK §7.3).

Numbers can only drift from the tables if they are copied, so nothing here is stored.
"""

import math
import re
from dataclasses import dataclass, field

from apps.forecasts.display import latest_accuracy
from apps.forecasts.models import ForecastPoint, ForecastRun
from apps.market.models import Asset, PriceBar

from . import formatting as fmt

MONTHLY_LAST_YEAR = 2030
YEARLY_LAST_YEAR = 2035
TREND_GAP_SHOWN = 10.0  # percent away from trend before the text mentions it

VERDICTS = {
    "strong_sell": "Strong Sell",
    "sell": "Sell",
    "neutral": "Neutral",
    "buy": "Buy",
    "strong_buy": "Strong Buy",
}
PHRASES = {
    "en": {
        "rise": "rise about {pct}",
        "fall": "fall about {pct}",
        "flat": "stay close to today's level",
        "above": "above",
        "below": "below",
        "rest_of": "the rest of {year}",
        "per": "per {unit}",
        "live_basis": "over {n} published forecasts",
        "backtest_basis": "in a test on {n} past dates",
        "noun_price": "price",
        "noun_stock": "stock price",
        "noun_rate": "exchange rate",
    },
}


class NoForecast(RuntimeError):
    pass


@dataclass
class Context:
    asset: Asset
    language: str
    run: ForecastRun
    seed: str
    values: dict = field(default_factory=dict)
    flags: dict = field(default_factory=dict)
    monthly: dict = field(default_factory=dict)  # method -> [points]


def milestone(price: float) -> float:
    """The next round price at least 50% above today: 1, 2 or 5 times a power of ten."""
    target = price * 1.5
    power = 10 ** math.floor(math.log10(target))
    return next(m * power for m in (1, 2, 5, 10) if m * power >= target)


def subject_of(asset: Asset) -> str:
    """How the asset reads inside a sentence: silver, Nvidia stock, Bitcoin, EUR/USD."""
    plain = re.sub(r"\s*\(.*\)$", "", asset.name)
    group = asset.asset_class.code
    if group in ("metal", "energy"):
        return plain.lower()
    if group == "stock":
        return f"{plain} stock"
    if group == "etf_index":
        return f"the {plain}"
    return asset.name if group == "fx" else plain


def noun_of(asset: Asset, phrases: dict) -> str:
    group = asset.asset_class.code
    if group == "stock":
        return phrases["noun_stock"]
    return phrases["noun_rate"] if group == "fx" else phrases["noun_price"]


def title_name(asset: Asset) -> str:
    """Bitcoin (BTC), but Crude oil (WTI) and IOTA stay as they are."""
    if re.search(rf"\b{re.escape(asset.code)}\b", asset.name):
        return asset.name
    return f"{asset.name} ({asset.code})"


def code_suffix(asset: Asset) -> str:
    """(BTC) after a name, unless the name or the pair already says it."""
    if asset.asset_class.code == "fx" or asset.code in asset.name:
        return ""
    return f" ({asset.code})"


def capitalise(text: str) -> str:
    return text[:1].upper() + text[1:]


def titlecase(text: str) -> str:
    return " ".join(capitalise(w) for w in text.split())


def build(asset: Asset, language: str = "en") -> Context:
    run = ForecastRun.objects.filter(asset=asset).exclude(model_version="small-site").order_by("-run_date").first()
    if run is None:
        raise NoForecast(asset.code)

    is_rate = asset.asset_class.code == "fx"
    phrases = PHRASES.get(language, PHRASES["en"])

    def money(v):
        return None if v is None else fmt.money(v, asset.currency, language, is_rate)

    def pct(fraction, signed=False):
        return None if fraction is None else fmt.percent(fraction, language, signed)

    today = run.last_close

    def move(target):
        if target is None:
            return None
        change = target / today - 1
        if abs(change) < 0.01:
            return phrases["flat"]
        return phrases["rise" if change > 0 else "fall"].format(pct=pct(change))

    def change_from_today(target):
        return None if target is None else pct(target / today - 1, signed=True)

    points = list(ForecastPoint.objects.filter(run=run, run_date=run.run_date).order_by("target"))
    daily = [p for p in points if p.horizon == "daily" and p.method == "consensus"]
    monthly = {}
    for p in points:
        if p.horizon == "monthly":
            monthly.setdefault(p.method, []).append(p)
    consensus_months = monthly.get("consensus", [])
    yearly = {(p.method, p.target.year): p for p in points if p.horizon == "yearly"}
    december = {p.target.year: p for p in consensus_months if p.target.month == 12}

    run_year = run.run_date.year
    tomorrow = next((p for p in daily if p.target > run.run_date), daily[0] if daily else None)
    last_daily = daily[-1] if daily else None
    peak = max(daily, key=lambda p: p.value) if daily else None
    end_year = december.get(run_year)
    months_2030 = [p for p in consensus_months if p.target.year == MONTHLY_LAST_YEAR]
    p90_2030 = max((p.p90 for p in months_2030), default=None)
    p10_2030 = min((p.p10 for p in months_2030), default=None)
    december_2030 = december.get(MONTHLY_LAST_YEAR)
    goal = milestone(today)

    bars = list(PriceBar.objects.filter(asset=asset).order_by("-date").values_list("close", flat=True)[:2])
    change_1d = float(bars[0]) / float(bars[1]) - 1 if len(bars) == 2 else None

    technicals = getattr(asset, "technicals", None)
    daily_ta = (technicals.timeframes.get("daily") if technicals else None) or {}

    def verdict(name):
        frame = (technicals.timeframes.get(name) if technicals else None) or {}
        code = frame.get("summary", {}).get("overall", {}).get("verdict")
        return VERDICTS.get(code)

    rsi = next((o["value"] for o in daily_ta.get("oscillators", []) if o["name"] == "rsi_14"), None)
    ma200 = next((m["simple"]["value"] for m in daily_ta.get("moving_averages", []) if m["period"] == 200), None)

    accuracy = latest_accuracy(asset)
    basis = None
    if accuracy:
        first = next(iter(accuracy.values()))
        key = "live_basis" if first.basis == "live" else "backtest_basis"
        basis = phrases[key].format(n=first.samples)

    reversion_params = (run.methods.get("reversion") or {}).get("params") or {}
    gap = reversion_params.get("deviation_from_trend_pct")
    mu = ((run.methods.get("montecarlo") or {}).get("params") or {}).get("mu_daily")
    yearly_consensus = [
        yearly[("consensus", y)]
        for y in range(MONTHLY_LAST_YEAR + 1, YEARLY_LAST_YEAR + 1)
        if ("consensus", y) in yearly
    ]
    first_long = yearly_consensus[0] if yearly_consensus else None
    last_long = yearly_consensus[-1] if yearly_consensus else None
    subject = subject_of(asset)
    noun = noun_of(asset, phrases)
    adr = getattr(asset, "adr", None)

    values = {
        "name": asset.name,
        "code": asset.code,
        "title_name": title_name(asset),
        "code_suffix": code_suffix(asset),
        "subject": subject,
        "Subject": capitalise(subject),
        "noun": noun,
        "Noun": titlecase(noun),
        "unit": asset.unit,
        "unit_label": phrases["per"].format(unit=asset.unit) if asset.unit and not is_rate else "",
        "year": run_year,
        "next_year": run_year + 1,
        "last_year": MONTHLY_LAST_YEAR,
        "last_yearly": YEARLY_LAST_YEAR,
        "date": fmt.long_date(run.data_date, language),
        "price": money(today),
        "change_1d": change_from_today(today * (1 + change_1d)) if change_1d is not None else None,
        "forecast_tomorrow": money(tomorrow.value if tomorrow else None),
        "tomorrow_date": fmt.long_date(tomorrow.target, language) if tomorrow else None,
        "tomorrow_low": money(tomorrow.p10 if tomorrow else None),
        "tomorrow_high": money(tomorrow.p90 if tomorrow else None),
        "forecast_30d": money(last_daily.value if last_daily else None),
        "date_30d": fmt.short_date(last_daily.target, language) if last_daily else None,
        "low_30d": money(last_daily.p10 if last_daily else None),
        "high_30d": money(last_daily.p90 if last_daily else None),
        "move_30d": move(last_daily.value if last_daily else None),
        "change_30d": change_from_today(last_daily.value if last_daily else None),
        "peak_30d": money(peak.value if peak else None),
        "forecast_end_year": money(end_year.value if end_year else None),
        "change_end_year": change_from_today(end_year.value if end_year else None),
        "p10_2030": money(p10_2030),
        "p90_2030": money(p90_2030),
        "goal": fmt.money_round(goal, asset.currency, language, is_rate),
        "long_first_year": first_long.target.year if first_long else None,
        "long_last_year": last_long.target.year if last_long else None,
        "long_first": money(first_long.value if first_long else None),
        "long_last": money(last_long.value if last_long else None),
        "reversion_last": money(yearly[("reversion", YEARLY_LAST_YEAR)].value)
        if ("reversion", YEARLY_LAST_YEAR) in yearly
        else None,
        "montecarlo_last": money(yearly[("montecarlo", YEARLY_LAST_YEAR)].value)
        if ("montecarlo", YEARLY_LAST_YEAR) in yearly
        else None,
        "p10_2035": money(last_long.p10 if last_long else None),
        "p90_2035": money(last_long.p90 if last_long else None),
        "ta_daily": verdict("daily"),
        "ta_weekly": verdict("weekly"),
        "ta_monthly": verdict("monthly"),
        "rsi": fmt.number(rsi, 2, language) if rsi is not None else None,
        "ma200": money(ma200),
        "ma200_side": (phrases["above"] if today > ma200 else phrases["below"]) if ma200 else None,
        "mape_1d": fmt.number(accuracy["1d"].mape, 2, language) if "1d" in accuracy else None,
        "mape_7d": fmt.number(accuracy["7d"].mape, 2, language) if "7d" in accuracy else None,
        "mape_30d": fmt.number(accuracy["30d"].mape, 2, language) if "30d" in accuracy else None,
        "accuracy_basis": basis,
        "trend_gap": pct(abs(gap) / 100) if gap is not None else None,
        "adr_symbol": adr.adr_asset.code if adr else None,
    }
    for year in range(run_year + 1, MONTHLY_LAST_YEAR + 1):
        values[f"forecast_{year}"] = money(december[year].value if year in december else None)
    for year in range(MONTHLY_LAST_YEAR + 1, YEARLY_LAST_YEAR + 1):
        point = yearly.get(("consensus", year))
        values[f"forecast_{year}"] = money(point.value if point else None)

    central = december_2030.value if december_2030 else 0
    upper = p90_2030 or 0
    flags = {
        "price_above_trend": gap is not None and gap > TREND_GAP_SHOWN,
        "price_below_trend": gap is not None and gap < -TREND_GAP_SHOWN,
        "montecarlo_up": mu is not None and mu > 0,
        "has_outlook": last_long is not None,
        "has_accuracy": bool(accuracy),
        "goal_central": central >= goal,
        "goal_possible": central < goal <= upper,
        "goal_unlikely": upper < goal,
        "is_adr": adr is not None,
        "is_index_etf": asset.asset_class.code == "etf_index",
        "close_only": bool(technicals and technicals.ohlc_basis == "close"),
    }
    return Context(asset, language, run, f"{asset.code}|{run.run_date}", values, flags, monthly)


def year_values(context: Context, year: int) -> dict | None:
    """Values for one calendar year of the monthly table, or None if the year has none."""
    rows = [p for p in context.monthly.get("consensus", []) if p.target.year == year]
    if not rows:
        return None
    asset, language = context.asset, context.language
    is_rate = asset.asset_class.code == "fx"
    phrases = PHRASES.get(language, PHRASES["en"])

    def money(v):
        return None if v is None else fmt.money(v, asset.currency, language, is_rate)

    def method_average(method):
        values = [p.value for p in context.monthly.get(method, []) if p.target.year == year]
        return money(sum(values) / len(values)) if values else None

    average = sum(p.value for p in rows) / len(rows)
    best, worst = max(rows, key=lambda p: p.value), min(rows, key=lambda p: p.value)
    december = next((p for p in rows if p.target.month == 12), None)
    return {
        "this_year": year,
        "period": str(year) if len(rows) == 12 else phrases["rest_of"].format(year=year),
        "year_avg": money(average),
        "year_change": fmt.percent(average / context.run.last_close - 1, language, signed=True),
        "year_best": money(best.value),
        "year_best_month": fmt.month_year(best.target, language),
        "year_worst": money(worst.value),
        "year_worst_month": fmt.month_year(worst.target, language),
        "year_low": money(min(p.p10 for p in rows)),
        "year_high": money(max(p.p90 for p in rows)),
        "year_december": money(december.value if december else None),
        "year_arima": method_average("arima"),
        "year_reversion": method_average("reversion"),
        "year_montecarlo": method_average("montecarlo"),
    }


VARIABLES = {
    "name",
    "code",
    "title_name",
    "code_suffix",
    "subject",
    "Subject",
    "noun",
    "Noun",
    "unit",
    "unit_label",
    "year",
    "next_year",
    "last_year",
    "last_yearly",
    "date",
    "price",
    "change_1d",
    "forecast_tomorrow",
    "tomorrow_date",
    "tomorrow_low",
    "tomorrow_high",
    "forecast_30d",
    "date_30d",
    "low_30d",
    "high_30d",
    "move_30d",
    "change_30d",
    "peak_30d",
    "forecast_end_year",
    "change_end_year",
    "p10_2030",
    "p90_2030",
    "goal",
    "long_first_year",
    "long_last_year",
    "long_first",
    "long_last",
    "reversion_last",
    "montecarlo_last",
    "p10_2035",
    "p90_2035",
    "ta_daily",
    "ta_weekly",
    "ta_monthly",
    "rsi",
    "ma200",
    "ma200_side",
    "mape_1d",
    "mape_7d",
    "mape_30d",
    "accuracy_basis",
    "trend_gap",
    "adr_symbol",
    *(f"forecast_{y}" for y in range(2027, YEARLY_LAST_YEAR + 1)),
}
YEAR_VARIABLES = {
    "this_year",
    "period",
    "year_avg",
    "year_change",
    "year_best",
    "year_best_month",
    "year_worst",
    "year_worst_month",
    "year_low",
    "year_high",
    "year_december",
    "year_arima",
    "year_reversion",
    "year_montecarlo",
}
FLAGS = {
    "price_above_trend",
    "price_below_trend",
    "montecarlo_up",
    "has_outlook",
    "has_accuracy",
    "goal_central",
    "goal_possible",
    "goal_unlikely",
    "is_adr",
    "is_index_etf",
    "close_only",
}
