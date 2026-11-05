"""Turns stored prices, forecasts and technicals into what the templates show."""

import math
from dataclasses import dataclass
from datetime import timedelta

from django.core.cache import cache
from django.db.models import OuterRef, Subquery
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.content import formatting as fmt
from apps.content.page import build_page
from apps.forecasts.display import for_display, recent_matured
from apps.forecasts.models import ForecastAccuracy, ForecastPoint, ForecastRun
from apps.market.models import Asset, PriceBar

from .caching import version

METHODS = ("arima", "reversion", "montecarlo")
LONG_METHODS = ("reversion", "montecarlo")
METHOD_LABELS = {
    "arima": "ARIMA",
    "reversion": "Trend + reversion",
    "montecarlo": "Monte Carlo",
    "consensus": "Consensus",
}
VERDICTS = {
    "strong_sell": "Strong Sell",
    "sell": "Sell",
    "neutral": "Neutral",
    "buy": "Buy",
    "strong_buy": "Strong Buy",
}
ACTIONS = {
    "buy": "Buy",
    "sell": "Sell",
    "neutral": "Neutral",
    "overbought": "Overbought",
    "oversold": "Oversold",
    "high_volatility": "High volatility",
    "low_volatility": "Low volatility",
}
OSCILLATORS = {
    "rsi_14": "RSI (14)",
    "stoch_9_6": "Stochastic (9, 6)",
    "stochrsi_14": "Stochastic RSI (14)",
    "macd_12_26": "MACD (12, 26)",
    "adx_14": "ADX (14)",
    "williams_r_14": "Williams %R (14)",
    "cci_14": "CCI (14)",
    "atr_14": "ATR (14)",
    "highs_lows_14": "Highs/Lows (14)",
    "ultimate_oscillator": "Ultimate Oscillator",
    "roc_12": "Rate of change (12)",
    "bull_bear_power_13": "Bull/Bear Power (13)",
}
PIVOTS = {
    "classic": "Classic",
    "fibonacci": "Fibonacci",
    "camarilla": "Camarilla",
    "woodie": "Woodie's",
    "demark": "DeMark",
}
PIVOT_LEVELS = ("s3", "s2", "s1", "p", "r1", "r2", "r3")
CLASS_PAGES = {
    "crypto": ("crypto", "Cryptocurrency price predictions"),
    "stock": ("stocks", "Stock price predictions"),
    "etf_index": ("indices-etf", "Stock index predictions"),
    "metal": ("metals", "Precious metal price predictions"),
    "energy": ("energy", "Energy price predictions"),
    "fx": ("currencies", "Currency forecasts"),
}
CLASS_ORDER = ("crypto", "stock", "metal", "energy", "etf_index", "fx")
COUNTRY_PAGES = {
    "us": ("US-listed stock predictions", "us"),
    "germany": ("German stock predictions", "de"),
}
HERO_IMAGES = {
    "crypto": "crypto-coin.svg",
    "stock": "stock-chart.svg",
    "etf_index": "stock-chart.svg",
    "fx": "stock-chart.svg",
    "energy": "stock-chart.svg",
}
CARDS_KEY = "web:cards"
CARDS_SECONDS = 3600
SPARK_BARS = 60
STALE_AFTER_DAYS = 4
VOLATILITY_BARS = {"crypto": 365, "nyse": 261, "fx": 261}
WEEK_BARS = {"crypto": 7, "nyse": 5, "fx": 5}
MONTH_BARS = {"crypto": 30, "nyse": 21, "fx": 21}
HALF_YEAR_BARS = {"crypto": 182, "nyse": 126, "fx": 126}


def asset_url(asset_or_slug) -> str:
    slug = getattr(asset_or_slug, "slug", asset_or_slug)
    return reverse("asset", args=[slug])


def direction(value) -> str:
    if value is None or abs(value) < 0.00005:
        return "flat"
    return "up" if value > 0 else "down"


def arrow(value) -> str:
    return {"up": "▲", "down": "▼", "flat": ""}[direction(value)]


@dataclass
class Numbers:
    """Formats one asset's numbers for one language."""

    asset: Asset
    language: str = "en"

    @property
    def is_rate(self) -> bool:
        return self.asset.asset_class.code == "fx"

    def money(self, value) -> str:
        if value is None:
            return "—"
        return fmt.money(float(value), self.asset.currency, self.language, self.is_rate)

    def percent(self, value) -> str:
        return "—" if value is None else fmt.percent(value, self.language, signed=True)

    def plain(self, value, digits=2) -> str:
        return "—" if value is None else fmt.number(float(value), digits, self.language)

    def signed(self, value) -> str:
        """▲ +1.20%"""
        return "—" if value is None else f"{arrow(value)} {self.percent(value)}".strip()

    def unit_short(self) -> str:
        return {"troy ounce": "/oz", "share": "/share", "barrel": "/bbl", "gallon": "/gal"}.get(self.asset.unit, "")

    def unit_label(self) -> str:
        if self.is_rate or not self.asset.unit:
            return ""
        return _("per %(unit)s") % {"unit": self.asset.unit}


def cell(text, tone="", strong=False) -> dict:
    return {"text": text, "tone": tone, "strong": strong}


def change_cell(numbers: Numbers, value, today) -> dict:
    if value is None:
        return cell("—")
    change = value / today - 1
    tone = direction(change)
    return cell(numbers.signed(change), "muted" if tone == "flat" else tone)


def table(caption, columns, rows, initial=None, note="", dark=False) -> dict:
    """columns: labels. The first column is the row header and is left aligned; a label ending < is too."""
    heads = []
    for i, label in enumerate(columns):
        left = i == 0 or label.endswith("<")
        heads.append({"label": label.rstrip("<"), "align": "left" if left else "right"})
    shaped = []
    for r, row in enumerate(rows):
        cells = []
        for i, value in enumerate(row):
            item = value if isinstance(value, dict) else cell(value)
            cells.append(item | {"align": heads[i]["align"], "header": i == 0})
        shaped.append({"cells": cells, "extra": initial is not None and r >= initial})
    return {
        "caption": caption,
        "columns": heads,
        "rows": shaped,
        "more": len(rows) if initial is not None and len(rows) > initial else 0,
        "note": note,
        "dark": dark,
    }


def sparkline(values: list[float], width=90, height=32) -> dict:
    if len(values) < 2:
        return {}
    low, high = min(values), max(values)
    span = (high - low) or 1
    step = width / (len(values) - 1)
    points = " ".join(
        f"{i * step:.1f},{height - 1 - (v - low) / span * (height - 2):.1f}" for i, v in enumerate(values)
    )
    return {"points": points, "width": width, "height": height, "trend": "up" if values[-1] >= values[0] else "down"}


def latest_runs():
    return ForecastRun.objects.exclude(model_version="small-site").order_by("-run_date")


def latest_run(asset):
    return latest_runs().filter(asset=asset).first()


def live_symbol(asset) -> str:
    """The Binance stream for a coin, for the price the browser updates by itself."""
    if asset.asset_class.code != "crypto":
        return ""
    symbol = asset.symbol if asset.source == "binance" else asset.fallback_symbol
    return symbol.lower() if symbol.endswith("USDT") else ""


def build_cards() -> list[dict]:
    last_run = Subquery(latest_runs().filter(asset=OuterRef("pk")).values("pk")[:1])
    pages = Asset.objects.filter(enabled=True, series_of=None).select_related("asset_class")
    cards = []
    for asset in pages.annotate(run_id=last_run):
        closes = list(
            PriceBar.objects.filter(asset=asset).order_by("-date").values_list("close", flat=True)[:SPARK_BARS]
        )
        if not closes:
            continue
        closes = [float(c) for c in reversed(closes)]
        numbers = Numbers(asset)
        price = closes[-1]
        change = price / closes[-2] - 1 if len(closes) > 1 else None
        target = None
        if asset.run_id:
            last = (
                ForecastPoint.objects.filter(run_id=asset.run_id, method="consensus", horizon="daily")
                .order_by("-target")
                .values_list("value", flat=True)
                .first()
            )
            target = last
        next_change = target / price - 1 if target else None
        cards.append(
            {
                "code": asset.code,
                "name": asset.name,
                "class": asset.asset_class.code,
                "country": asset.country,
                "url": asset_url(asset),
                "price": numbers.money(price),
                "unit": numbers.unit_short(),
                "change": numbers.signed(change),
                "dir": direction(change),
                "next": numbers.money(target),
                "next_change": numbers.percent(next_change),
                "next_dir": direction(next_change),
                "spark": sparkline(closes),
                "color": asset.color,
                "live": bool(asset.live_symbol),
                "stream": live_symbol(asset),
                "raw_price": price,
            }
        )
    return cards


def cards() -> list[dict]:
    key = f"{CARDS_KEY}:{version()}"
    found = cache.get(key)
    if found is None:
        found = build_cards()
        cache.set(key, found, CARDS_SECONDS)
    return found


def cards_by_class() -> list[dict]:
    everything = cards()
    groups = []
    for code in CLASS_ORDER:
        path, title = CLASS_PAGES[code]
        items = [c for c in everything if c["class"] == code]
        if items:
            groups.append({"code": code, "title": _(title), "url": f"/{path}/", "cards": items})
    return groups


def point_map(run) -> dict:
    out = {}
    for p in ForecastPoint.objects.filter(run=run, run_date=run.run_date).order_by("target"):
        out.setdefault((p.method, p.horizon), []).append(p)
    return out


def daily_table(numbers, points, today, name) -> dict:
    by_method = {m: {p.target: p for p in points.get((m, "daily"), [])} for m in METHODS}
    rows = []
    for p in points.get(("consensus", "daily"), []):
        label = fmt.short_date(p.target, numbers.language)
        values = [numbers.money(by_method[m][p.target].value if p.target in by_method[m] else None) for m in METHODS]
        spread = f"{numbers.money(p.p10)} – {numbers.money(p.p90)}"
        rows.append(
            [
                label,
                *values,
                cell(numbers.money(p.value), strong=True),
                cell(spread, "muted"),
                change_cell(numbers, p.value, today),
            ]
        )
    columns = [_("Date"), *[_(METHOD_LABELS[m]) for m in METHODS], _("Consensus"), _("Range (P10–P90)"), _("vs today")]
    note = _("Consensus = average of the three models. Range = 80% of model outcomes (P10–P90).")
    return table(
        _("%(name)s daily forecast for the next 30 days") % {"name": name}, columns, rows, initial=10, note=note
    )


def monthly_table(numbers, rows_for_year, today, name, year, dark=False, initial=None) -> dict:
    rows = [
        [
            fmt.month_year(p.target, numbers.language),
            numbers.money(p.p10),
            cell(numbers.money(p.value), strong=True),
            numbers.money(p.p90),
            change_cell(numbers, p.value, today),
        ]
        for p in rows_for_year
    ]
    columns = [_("Month"), _("Low"), _("Average"), _("High"), _("vs today")]
    caption = _("%(name)s monthly forecast %(year)s") % {"name": name, "year": year}
    return table(caption, columns, rows, dark=dark, initial=initial)


def year_summary_table(numbers, points, today, name, years) -> dict:
    rows = []
    for year in years:
        row = [str(year)]
        for method in (*METHODS, "consensus"):
            values = [p.value for p in points.get((method, "monthly"), []) if p.target.year == year]
            value = sum(values) / len(values) if values else None
            row.append(cell(numbers.money(value), strong=method == "consensus"))
        consensus = [p.value for p in points.get(("consensus", "monthly"), []) if p.target.year == year]
        row.append(change_cell(numbers, sum(consensus) / len(consensus) if consensus else None, today))
        rows.append(row)
    columns = [_("Year"), *[_(METHOD_LABELS[m]) for m in METHODS], _("Consensus"), _("vs today")]
    return table(_("Average %(name)s forecast per year and model") % {"name": name}, columns, rows)


def long_term_table(numbers, points, name) -> dict | None:
    consensus = points.get(("consensus", "yearly"), [])
    if not consensus:
        return None
    by_method = {m: {p.target: p for p in points.get((m, "yearly"), [])} for m in LONG_METHODS}
    rows = []
    for p in consensus:
        values = [
            numbers.money(by_method[m][p.target].value if p.target in by_method[m] else None) for m in LONG_METHODS
        ]
        rows.append(
            [
                str(p.target.year),
                *values,
                cell(numbers.money(p.value), strong=True),
                cell(f"{numbers.money(p.p10)} – {numbers.money(p.p90)}", "muted"),
            ]
        )
    columns = [_("Year"), *[_(METHOD_LABELS[m]) for m in LONG_METHODS], _("Consensus"), _("Range (P10–P90)")]
    note = _("Long-run models only: ARIMA adds no information at this range.")
    return table(_("%(name)s yearly forecast") % {"name": name}, columns, rows, note=note, dark=True)


def accuracy_table(asset, numbers) -> dict | None:
    rows = {}
    labels = ("1d", "7d", "30d")
    live = False
    for r in for_display(asset):
        if r.horizon in labels:
            rows.setdefault(r.method, {})[r.horizon] = r
            live = live or r.basis == ForecastAccuracy.Basis.LIVE
    if not rows:
        return None
    shaped = [
        [_(METHOD_LABELS[m]), *[f"{numbers.plain(rows[m][h].mape if h in rows[m] else None)}%" for h in labels]]
        for m in (*METHODS, "consensus")
        if m in rows
    ]
    note = (
        _("Based on published forecasts.")
        if live
        else _(
            "Walk-forward test: models refit on past data only. A live track record replaces it as forecasts mature."
        )
    )
    return table(
        _("Average forecast error (MAPE)"), [_("Method"), _("1 day"), _("7 days"), _("30 days")], shaped, note=note
    )


def matured_table(asset, numbers) -> dict | None:
    rows = recent_matured(asset)
    if not rows:
        return None
    shaped = [
        [
            fmt.short_date(r["target"], numbers.language),
            numbers.money(r["forecast"]),
            numbers.money(r["actual"]),
            cell(numbers.percent(r["forecast"] / r["actual"] - 1), "muted"),
        ]
        for r in rows
    ]
    columns = [_("Date"), _("Forecast"), _("Actual"), _("Difference")]
    note = _("The consensus for the next day, as published, against the close that followed.")
    return table(_("Recent forecasts against real prices"), columns, shaped, note=note, initial=5)


def history_rows(bars) -> list[dict]:
    """Average, high, low and change per calendar year, newest first."""
    years = {}
    for day, close in bars:
        years.setdefault(day.year, []).append(float(close))
    keys = sorted(years)
    out = []
    for year in keys[-10:][::-1]:
        closes = years[year]
        previous = years.get(year - 1)
        start = previous[-1] if previous else closes[0]
        out.append(
            {
                "year": year,
                "avg": sum(closes) / len(closes),
                "high": max(closes),
                "low": min(closes),
                "change": closes[-1] / start - 1,
            }
        )
    return out


def history_table(numbers, bars, name) -> dict:
    rows = [
        [
            str(y["year"]),
            numbers.money(y["avg"]),
            numbers.money(y["high"]),
            numbers.money(y["low"]),
            change_cell(numbers, 1 + y["change"], 1),
        ]
        for y in history_rows(bars)
    ]
    columns = [_("Year"), _("Average"), _("High"), _("Low"), _("Change")]
    return table(_("%(name)s price history by year") % {"name": name}, columns, rows, initial=5)


def extremes(bars) -> dict | None:
    """Largest one-day move and deepest fall from a peak."""
    if len(bars) < 2:
        return None
    biggest, biggest_day = 0.0, None
    peak, peak_day = float(bars[0][1]), bars[0][0]
    deepest, deepest_from, deepest_to = 0.0, None, None
    previous = float(bars[0][1])
    for day, close in bars[1:]:
        close = float(close)
        move = close / previous - 1
        if abs(move) > abs(biggest):
            biggest, biggest_day = move, day
        if close > peak:
            peak, peak_day = close, day
        fall = close / peak - 1
        if fall < deepest:
            deepest, deepest_from, deepest_to = fall, peak_day, day
        previous = close
    return {
        "since": bars[0][0],
        "move": biggest,
        "move_day": biggest_day,
        "fall": deepest,
        "from": deepest_from,
        "to": deepest_to,
    }


def change_over(closes: list[float], steps: int):
    if len(closes) <= steps:
        return None
    return closes[-1] / closes[-1 - steps] - 1


def chart_header(asset, numbers, bars) -> dict:
    last = PriceBar.objects.filter(asset=asset).order_by("-date").first()
    closes = [float(c) for _, c in bars]
    rel = change_over(closes, 1)
    calendar = asset.asset_class.calendar
    this_year = [c for d, c in bars if d.year == last.date.year]
    before = [float(c) for d, c in bars if d.year < last.date.year]
    year_to_date = closes[-1] / before[-1] - 1 if before and this_year else None
    periods = [
        (_("1 day"), rel),
        (_("1 week"), change_over(closes, WEEK_BARS[calendar])),
        (_("1 month"), change_over(closes, MONTH_BARS[calendar])),
        (_("6 months"), change_over(closes, HALF_YEAR_BARS[calendar])),
        (_("Year to date"), year_to_date),
    ]
    return {
        "price": numbers.money(last.close),
        "unit": numbers.unit_short(),
        "arrow": arrow(rel),
        "dir": direction(rel),
        "change": numbers.percent(rel),
        "abs": numbers.money(abs(float(last.close) - closes[-2])) if len(closes) > 1 else "—",
        "high": numbers.money(last.high),
        "low": numbers.money(last.low),
        "date": fmt.long_date(last.date, numbers.language),
        "estimated": last.basis in ("proxy", "estimate"),
        "periods": [{"label": label, "text": numbers.signed(v), "dir": direction(v)} for label, v in periods],
    }


def gauge(title: str, tally: dict) -> dict:
    total = tally["buy"] + tally["sell"] + tally["neutral"]
    score = (tally["buy"] - tally["sell"]) / total if total else 0
    radius, cx, cy, gap = 80, 100, 96, 2
    colors = ("#ef4444", "#f4a3a3", "#cccdce", "#9fe3c6", "#16c47f")

    def at(degrees, r=radius):
        rad = math.radians(degrees)
        return cx + r * math.cos(rad), cy - r * math.sin(rad)

    arcs = []
    for i, color in enumerate(colors):
        a0 = 180 - i * 36 - (gap / 2 if i else 0)
        a1 = 180 - (i + 1) * 36 + (gap / 2 if i < 4 else 0)
        x0, y0 = at(a0)
        x1, y1 = at(a1)
        arcs.append({"color": color, "d": f"M{x0:.2f} {y0:.2f} A{radius} {radius} 0 0 1 {x1:.2f} {y1:.2f}"})
    nx, ny = at(90 - score * 90, radius - 18)
    verdict = tally["verdict"]
    tone = "buy" if "buy" in verdict else "sell" if "sell" in verdict else "neutral"
    return {
        "title": title,
        "arcs": arcs,
        "nx": f"{nx:.2f}",
        "ny": f"{ny:.2f}",
        "verdict": _(VERDICTS[verdict]),
        "tone": tone,
        "buy": tally["buy"],
        "neutral": tally["neutral"],
        "sell": tally["sell"],
    }


def action_cell(action) -> dict:
    if action is None:
        return cell("—")
    tone = "buy" if action == "buy" else "sell" if action == "sell" else "muted"
    return cell(_(ACTIONS.get(action, action)), tone)


def technical_panels(asset, numbers, snapshot) -> list[dict]:
    if snapshot is None:
        return []
    panels = []
    labels = {"daily": _("Daily"), "weekly": _("Weekly"), "monthly": _("Monthly")}
    name = asset.name
    for key, label in labels.items():
        frame = snapshot.timeframes.get(key)
        if not frame:
            continue
        summary = frame["summary"]
        oscillators = [
            [
                _(OSCILLATORS.get(o["name"], o["name"])),
                numbers.plain(o["value"], 3 if abs(o["value"] or 0) < 10 else 2),
                action_cell(o["action"]),
            ]
            for o in frame["oscillators"]
        ]
        averages = [
            [
                f"MA{m['period']}",
                numbers.money(m["simple"]["value"]),
                action_cell(m["simple"]["action"]),
                numbers.money(m["exponential"]["value"]),
                action_cell(m["exponential"]["action"]),
            ]
            for m in frame["moving_averages"]
        ]
        pivots = [
            [_(PIVOTS.get(kind, kind)), *[cell(numbers.money(levels.get(k)), strong=k == "p") for k in PIVOT_LEVELS]]
            for kind, levels in frame["pivots"].items()
        ]
        tables = [
            table(f"{name}: " + _("technical indicators"), [_("Name"), _("Value"), _("Action")], oscillators),
            table(f"{name}: " + _("moving averages"), [_("Period"), _("Simple"), "", _("Exponential"), ""], averages),
        ]
        pivot_table = None
        if pivots:
            heads = [_("Name"), "S3", "S2", "S1", _("Pivot"), "R1", "R2", "R3"]
            pivot_table = table(f"{name}: " + _("pivot points"), heads, pivots)
        panels.append(
            {
                "key": key,
                "label": label,
                "gauges": [
                    gauge(_("Summary"), summary["overall"]),
                    gauge(_("Technical indicators"), summary["oscillators"]),
                    gauge(_("Moving averages"), summary["moving_averages"]),
                ],
                "tables": tables,
                "pivots": pivot_table,
            }
        )
    return panels


def analyst_table(asset, numbers, entries) -> dict | None:
    if not entries:
        return None
    rows = []
    for e in entries:
        target = (
            numbers.money(e["target"])
            if e["target"] is not None
            else f"{numbers.money(e['target_low'])} – {numbers.money(e['target_high'])}"
        )
        rows.append(
            [
                e["institution"],
                e["horizon"],
                cell(target, strong=True),
                e["basis"],
                fmt.short_date(e["published_on"], numbers.language),
            ]
        )
    columns = [_("Institution"), _("Horizon<"), _("Target"), _("Basis"), _("Published")]
    return table(_("Published %(name)s price targets") % {"name": asset.name}, columns, rows)


def asset_page(asset, language="en") -> dict:
    page = build_page(asset, language)
    numbers = Numbers(asset, language)
    run = latest_run(asset)
    points = point_map(run)
    today = run.last_close
    name = asset.name
    bars = list(PriceBar.objects.filter(asset=asset).order_by("date").values_list("date", "close"))
    consensus_months = points.get(("consensus", "monthly"), [])
    daily = points.get(("consensus", "daily"), [])
    run_year = run.run_date.year

    december = {p.target.year: p for p in consensus_months if p.target.month == 12}
    in_30 = daily[-1].value if daily else None
    end_year = december[run_year].value if run_year in december else None
    last_year = max(december) if december else run_year
    end_last = december[last_year].value if december else None

    def glance(label, value, meta):
        change = value / today - 1 if value else None
        return {
            "label": label,
            "value": numbers.money(value),
            "unit": numbers.unit_label(),
            "meta": meta,
            "change": numbers.signed(change),
            "dir": direction(change),
        }

    updated = _("Last updated: %(date)s") % {"date": fmt.long_date(run.run_date, language)}
    year_blocks = []
    later = [y for y in page["years"] if y["year"] > run_year]
    for block in page["years"]:
        rows = [p for p in consensus_months if p.target.year == block["year"]]
        first = block["year"] == run_year
        last = block["year"] == last_year
        position = later.index(block) if block in later else 0
        value = december[block["year"]].value if block["year"] in december else None
        label = _("Forecast end of %(year)s") % {"year": block["year"]}
        year_blocks.append(
            block
            | {
                "first": first,
                "dark": last,
                "reverse": not first and (position % 2 == 1 or last),
                "variant": "dark" if last else ("soft" if first or position % 2 == 0 else "white"),
                "card": glance(label, value, _("December %(year)s average") % {"year": block["year"]}),
                "table": monthly_table(
                    numbers, rows, today, name, block["year"], dark=last, initial=None if first else 6
                ),
            }
        )

    snapshot = getattr(asset, "technicals", None)
    daily_frame = (snapshot.timeframes.get("daily") if snapshot else None) or {}
    verdict = daily_frame.get("summary", {}).get("overall", {}).get("verdict")
    closes = [float(c) for _, c in bars]
    sigma = ((run.methods.get("montecarlo") or {}).get("params") or {}).get("sigma_daily")
    calendar = asset.asset_class.calendar
    volatility = sigma * math.sqrt(VOLATILITY_BARS[calendar]) if sigma else None
    span = extremes(bars)
    tomorrow = next((p for p in daily if p.target > run.run_date), daily[0] if daily else None)
    week = next(
        (p for p in daily if tomorrow and p.target >= tomorrow.target + timedelta(days=6)), daily[-1] if daily else None
    )

    def near(point, label):
        if point is None:
            return None
        return {
            "label": label,
            "date": fmt.short_date(point.target, language),
            "value": numbers.money(point.value),
            "low": numbers.money(point.p10),
            "high": numbers.money(point.p90),
        }

    risk_note = None
    if span and span["move_day"] and span["from"]:
        risk_note = _(
            "Prices can fall sharply: in our data since %(since)s the largest one-day move was %(move)s "
            "(%(move_day)s), and the deepest fall from a peak was %(fall)s (%(start)s to %(end)s)."
        ) % {
            "since": fmt.month_year(span["since"], language),
            "move": numbers.percent(span["move"]),
            "move_day": fmt.long_date(span["move_day"], language),
            "fall": numbers.percent(span["fall"]),
            "start": fmt.long_date(span["from"], language),
            "end": fmt.long_date(span["to"], language),
        }

    age = (timezone.now().date() - run.data_date).days
    related = [c for c in cards() if c["class"] == asset.asset_class.code and c["code"] != asset.code][:4]
    blocks_after = {}
    for block in page["blocks"]:
        blocks_after.setdefault(block["after"], []).append(block)

    return {
        "asset": asset,
        "page": page,
        "stale": age > STALE_AFTER_DAYS,
        "data_date": fmt.long_date(run.data_date, language),
        "updated": fmt.long_date(run.run_date, language),
        "hero_image": HERO_IMAGES.get(asset.asset_class.code)
        or ("gold-bars.svg" if asset.code == "XAU" else "silver-bars.svg"),
        "glance": [
            glance(_("In 30 days"), in_30, updated),
            glance(
                _("End of %(year)s") % {"year": run_year}, end_year, _("December %(year)s average") % {"year": run_year}
            ),
            glance(str(last_year), end_last, _("December %(year)s average") % {"year": last_year}),
        ],
        "verdict": _(VERDICTS[verdict]) if verdict else None,
        "verdict_tone": "buy"
        if verdict and "buy" in verdict
        else "sell"
        if verdict and "sell" in verdict
        else "neutral",
        "chart": chart_header(asset, numbers, bars) if closes else None,
        "chart_color": asset.color or "#8a96a8",
        "tomorrow": near(tomorrow, _("Tomorrow")),
        "week": near(week, _("In one week")),
        "daily_table": daily_table(numbers, points, today, name),
        "years": year_blocks,
        "this_year": next((y for y in year_blocks if y["first"]), None),
        "later_years": [y for y in year_blocks if not y["first"]],
        "summary_table": year_summary_table(numbers, points, today, name, [y["year"] for y in page["years"]]),
        "long_term_table": long_term_table(numbers, points, name),
        "technical_panels": technical_panels(asset, numbers, snapshot),
        "analysts_table": analyst_table(asset, numbers, page["analysts"]),
        "history_table": history_table(numbers, bars, name),
        "accuracy_table": accuracy_table(asset, numbers),
        "matured_table": matured_table(asset, numbers),
        "volatility": fmt.percent(volatility, language) if volatility else None,
        "risk_note": risk_note,
        "related": related,
        "blocks_after": blocks_after,
        "live_stream": live_symbol(asset),
        "live_quote": bool(asset.live_symbol),
        "raw_price": closes[-1] if closes else None,
    }


def chart_data(asset) -> dict:
    run = latest_run(asset)
    history = [
        [str(d), float(c)]
        for d, c in PriceBar.objects.filter(asset=asset).order_by("date").values_list("date", "close")
    ]
    forecast = {m: [] for m in (*METHODS, "consensus", "low", "high")}
    if run:
        points = point_map(run)
        last_daily = max((p.target for p in points.get(("consensus", "daily"), [])), default=None)
        for method in (*METHODS, "consensus"):
            for p in points.get((method, "daily"), []):
                forecast[method].append([str(p.target), p.value])
                if method == "consensus":
                    forecast["low"].append([str(p.target), p.p10])
                    forecast["high"].append([str(p.target), p.p90])
            for p in points.get((method, "monthly"), []):
                if last_daily is None or p.target > last_daily:
                    forecast[method].append([str(p.target), p.value])
                    if method == "consensus":
                        forecast["low"].append([str(p.target), p.p10])
                        forecast["high"].append([str(p.target), p.p90])
    return {"history": history, "forecast": forecast}


def versus(numbers, value, today) -> str:
    return numbers.percent(value / today - 1) if value and today else "—"


def compare(left, right, language="en") -> dict:
    rows = []
    sides = []
    for asset in (left, right):
        numbers = Numbers(asset, language)
        run = latest_run(asset)
        points = point_map(run) if run else {}
        daily = points.get(("consensus", "daily"), [])
        months = points.get(("consensus", "monthly"), [])
        december = {p.target.year: p for p in months if p.target.month == 12}
        today = run.last_close if run else None
        sigma = ((run.methods.get("montecarlo") or {}).get("params") or {}).get("sigma_daily") if run else None
        accuracy = {r.horizon: r for r in for_display(asset) if r.method == "consensus"}

        sides.append(
            {
                "name": asset.name,
                "url": asset_url(asset),
                "cells": [
                    numbers.money(today),
                    numbers.money(daily[-1].value if daily else None),
                    versus(numbers, daily[-1].value if daily else None, today),
                    numbers.money(december[2030].value if 2030 in december else None),
                    versus(numbers, december[2030].value if 2030 in december else None, today),
                    fmt.percent(sigma * math.sqrt(VOLATILITY_BARS[asset.asset_class.calendar]), language)
                    if sigma
                    else "—",
                    f"{numbers.plain(accuracy['30d'].mape)}%" if "30d" in accuracy else "—",
                ],
            }
        )
    labels = [
        _("Latest close"),
        _("Consensus in 30 days"),
        _("Change in 30 days"),
        _("Consensus December 2030"),
        _("Change to 2030"),
        _("Yearly volatility"),
        _("Typical 30-day error"),
    ]
    for i, label in enumerate(labels):
        rows.append([label, sides[0]["cells"][i], sides[1]["cells"][i]])
    return {
        "left": sides[0],
        "right": sides[1],
        "table": table(_("Forecast comparison"), [_("Measure"), left.name, right.name], rows),
    }


def accuracy_overview(language="en") -> dict:
    rows = ForecastAccuracy.objects.filter(method="consensus", horizon="30d", basis="backtest").select_related("asset")
    ranked = sorted(rows, key=lambda r: r.mape)
    assets = [
        [
            cell(r.asset.name),
            f"{fmt.number(r.mape, 2, language)}%",
            f"{fmt.number(r.direction_pct, 0, language)}%" if r.direction_pct is not None else "—",
            str(r.samples),
        ]
        for r in ranked
        if r.asset.series_of_id is None
    ]
    methods = []
    all_rows = list(ForecastAccuracy.objects.filter(basis="backtest", horizon__in=("1d", "7d", "30d")))
    for method in (*METHODS, "consensus"):
        chosen = [r for r in all_rows if r.method == method]
        row = [_(METHOD_LABELS[method])]
        for horizon in ("1d", "7d", "30d"):
            values = [r.mape for r in chosen if r.horizon == horizon]
            row.append(f"{fmt.number(sum(values) / len(values), 2, language)}%" if values else "—")
        direction_values = [r.direction_pct for r in chosen if r.horizon == "30d" and r.direction_pct is not None]
        row.append(
            f"{fmt.number(sum(direction_values) / len(direction_values), 0, language)}%" if direction_values else "—"
        )
        methods.append(row)
    return {
        "methods": table(
            _("Average error by model, all assets"),
            [_("Model"), _("1 day"), _("7 days"), _("30 days"), _("Direction right, 30 days")],
            methods,
        ),
        "assets": table(
            _("30-day consensus error by asset, lowest first"),
            [_("Asset"), _("Average error"), _("Direction right"), _("Test dates")],
            assets,
            initial=20,
        ),
        "live_count": ForecastAccuracy.objects.filter(
            basis="live", method="consensus", horizon="1d", window_days=365
        ).count(),
    }
