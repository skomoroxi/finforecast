"""Numbers and dates by language (TECHNICAL-TASK §7.3): $1,234.56 in English, 1.234,56 $ in German."""

from datetime import date

MONTHS = {
    "en": "January February March April May June July August September October November December".split(),
    "de": "Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split(),
}
SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}


def number(value: float, digits: int = 2, lang: str = "en") -> str:
    text = f"{value:,.{digits}f}"
    if lang == "de":
        text = text.replace(",", "\0").replace(".", ",").replace("\0", ".")
    return text


def digits_for(value: float) -> int:
    """Precision follows the price level: 81,344 · 254.60 · 1.326 · 0.0798 · 0.00000473."""
    size = abs(value)
    if size >= 1000:
        return 0
    if size >= 10:
        return 2
    if size >= 1:
        return 3
    if size >= 0.01 or size == 0:
        return 4
    text = f"{size:.2e}"
    return min(12, 2 - int(text.split("e")[1]))


def with_currency(text: str, currency: str, lang: str) -> str:
    symbol = SYMBOLS.get(currency, currency)
    if lang == "de":
        return f"{text} {symbol}"
    return f"{symbol}{text}" if symbol in SYMBOLS.values() else f"{text} {symbol}"


def money(value: float, currency: str, lang: str = "en", is_rate: bool = False) -> str:
    """A price. Exchange rates have no currency sign and four decimals."""
    if is_rate:
        return number(value, 4, lang)
    return with_currency(number(value, digits_for(value), lang), currency, lang)


def money_round(value: float, currency: str, lang: str = "en", is_rate: bool = False) -> str:
    """A round target: $500, $0.20, $0.005."""
    digits = 0 if value >= 1 else (2 if value >= 0.01 else digits_for(value))
    if is_rate:
        return number(value, 2, lang)
    return with_currency(number(value, digits, lang), currency, lang)


def percent(fraction: float, lang: str = "en", signed: bool = False) -> str:
    text = number(abs(fraction) * 100, 2, lang)
    sign = ("+" if fraction >= 0 else "−") if signed else ""
    return f"{sign}{text} %" if lang == "de" else f"{sign}{text}%"


def long_date(day: date, lang: str = "en") -> str:
    month = MONTHS[lang][day.month - 1]
    return f"{day.day}. {month} {day.year}" if lang == "de" else f"{month} {day.day}, {day.year}"


def short_date(day: date, lang: str = "en") -> str:
    month = MONTHS[lang][day.month - 1]
    return f"{day.day}. {month}" if lang == "de" else f"{month} {day.day}"


def month_year(day: date, lang: str = "en") -> str:
    return f"{MONTHS[lang][day.month - 1]} {day.year}"
