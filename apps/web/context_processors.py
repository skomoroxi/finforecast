"""Navigation and the price bar. Lazy, so the admin never pays for them."""

from django.utils.functional import SimpleLazyObject

from . import data

TICKER_CODES = ("BTC", "ETH", "XAU", "XAG", "WTI", "SPY", "NVDA", "EURUSD")
MENU_ITEMS = 10


def nav_groups():
    groups = data.cards_by_class()
    return [g | {"cards": g["cards"][:MENU_ITEMS]} for g in groups]


def ticker():
    by_code = {c["code"]: c for c in data.cards()}
    return [by_code[c] for c in TICKER_CODES if c in by_code]


def site_chrome(request):
    return {"nav_groups": SimpleLazyObject(nav_groups), "ticker_items": SimpleLazyObject(ticker)}
