"""The approved launch catalog (TECHNICAL-TASK §3.1). `seed_assets` loads it; the admin owns it afterwards."""

import re
from datetime import date

CLASSES = [
    # code, name, calendar, default unit, max daily change
    ("crypto", "Cryptocurrencies", "crypto", "coin", 0.6),
    ("stock", "Stocks", "nyse", "share", 0.4),
    ("etf_index", "Indices", "nyse", "share", 0.2),
    ("fx", "Currency pairs", "fx", "", 0.15),
    ("metal", "Metals", "fx", "troy ounce", 0.35),
    ("energy", "Energy", "fx", "barrel", 0.45),
]

# code, name. Twelve Data symbol is CODE/USD; the Binance fallback is CODEUSDT.
CRYPTO_TD = [
    ("BTC", "Bitcoin"),
    ("ETH", "Ethereum"),
    ("XRP", "XRP (Ripple)"),
    ("SOL", "Solana"),
    ("ADA", "Cardano"),
    ("DOGE", "Dogecoin"),
    ("SHIB", "Shiba Inu"),
    ("TRX", "Tron"),
    ("LTC", "Litecoin"),
    ("BCH", "Bitcoin Cash"),
    ("XLM", "Stellar"),
    ("LINK", "Chainlink"),
    ("DOT", "Polkadot"),
    ("UNI", "Uniswap"),
    ("RENDER", "Render"),
    ("XTZ", "Tezos"),
    ("VET", "VeChain"),
    ("GRT", "The Graph"),
    ("RUNE", "THORChain"),
    ("SUI", "Sui"),
    ("QNT", "Quant"),
    ("FET", "Fetch.ai (ASI)"),
    ("IOTA", "IOTA"),
    ("DASH", "Dash"),
    ("NEO", "NEO"),
    ("S", "Sonic (Fantom)"),
]

CRYPTO_BINANCE = [
    ("EOS", "EOS (Vaulta)"),
    ("TON", "Toncoin"),
    ("HMSTR", "Hamster Kombat"),
    ("BONK", "Bonk"),
    ("FLOKI", "Floki"),
    ("TURBO", "Turbo"),
    ("TRUMP", "Official Trump"),
]

STOCKS_US = [
    ("AAPL", "Apple"),
    ("MSFT", "Microsoft"),
    ("GOOGL", "Alphabet (Google)"),
    ("AMZN", "Amazon"),
    ("META", "Meta"),
    ("NVDA", "Nvidia"),
    ("TSLA", "Tesla"),
    ("AMD", "AMD"),
    ("INTC", "Intel"),
    ("NFLX", "Netflix"),
    ("PLTR", "Palantir"),
    ("PYPL", "PayPal"),
    ("KO", "Coca-Cola"),
    ("MRNA", "Moderna"),
    ("CCL", "Carnival"),
    ("CGC", "Canopy Growth"),
    ("CRCL", "Circle"),
    ("MSTR", "Strategy (MicroStrategy)"),
    ("DB", "Deutsche Bank"),
    ("NVO", "Novo Nordisk"),
    ("TSM", "TSMC"),
    ("BNTX", "BioNTech"),
    ("SAP", "SAP"),
]

# Quoted in USD through their OTC ADR, no XETRA line to estimate.
STOCKS_ASIA_ADR = [
    ("XIACY", "Xiaomi"),
    ("LNVGY", "Lenovo"),
    ("BYDDY", "BYD"),
]

# code, name, ADR symbol, XETRA symbol. Priced in euros from the ADR.
STOCKS_GERMAN = [
    ("BMW", "BMW", "BMWKY", "BMW.DEX"),
    ("BAS", "BASF", "BASFY", "BAS.DEX"),
    ("ADS", "adidas", "ADDYY", "ADS.DEX"),
    ("P911", "Porsche AG", "DRPRY", "P911.DEX"),
    ("MBG", "Mercedes-Benz", "MBGYY", "MBG.DEX"),
    ("VOW3", "Volkswagen", "VWAGY", "VOW3.DEX"),
    ("RHM", "Rheinmetall", "RNMBY", "RHM.DEX"),
    ("HAG", "Hensoldt", "HAGHY", "HAG.DEX"),
    ("R3NK", "Renk", "RNKGF", "R3NK.DEX"),
    ("LHA", "Lufthansa", "DLAKY", "LHA.DEX"),
    ("ALV", "Allianz", "ALIZY", "ALV.DEX"),
    ("BAYN", "Bayer", "BAYRY", "BAYN.DEX"),
    ("DTE", "Deutsche Telekom", "DTEGY", "DTE.DEX"),
    ("SIE", "Siemens", "SIEGY", "SIE.DEX"),
]

INDEX_ETFS = [
    ("QQQ", "Nasdaq 100"),
    ("SPY", "S&P 500"),
    ("DAX", "DAX"),
]

# Addresses the small site already has keep exactly this form.
SLUGS = {"NVDA": "nvidia-stock-forecast"}
FX_PAIRS = ["EUR/USD", "EUR/BRL", "EUR/PLN", "EUR/TRY", "EUR/GBP", "EUR/CHF"]


def slug_for(row: dict) -> str:
    if row["code"] in SLUGS:
        return SLUGS[row["code"]]
    plain = re.sub(r"\s*\(.*\)$", "", row["name"]).lower()
    plain = re.sub(r"[^a-z0-9]+", "-", plain.replace("&", "")).strip("-")
    if row["asset_class"] == "fx":
        return f"{plain}-forecast"
    middle = "stock-price" if row["asset_class"] == "stock" else "price"
    return f"{plain}-{middle}-prediction"


def asset_rows() -> list[dict]:
    """Every catalog asset, in display order. `series_of` and `proxy` are codes, resolved by seed_assets."""
    rows = []

    def add(code, name, asset_class, source, symbol, **extra):
        rows.append(
            {"code": code, "name": name, "asset_class": asset_class, "source": source, "symbol": symbol, **extra}
        )

    for code, name in CRYPTO_TD:
        add(
            code,
            name,
            "crypto",
            "twelvedata",
            f"{code}/USD",
            fallback_source="binance",
            fallback_symbol=f"{code}USDT",
        )
    for code, name in CRYPTO_BINANCE:
        add(code, name, "crypto", "binance", f"{code}USDT")

    by_code = {r["code"]: r for r in rows}
    # Twelve Data's S/USD before Sonic's launch is an unrelated token; history is Fantom's on Binance.
    by_code["S"].update(history_source="binance", history_symbol="FTMUSDT", main_from=date(2025, 1, 14))
    # EOS became Vaulta (ticker A) in May 2025; Binance stopped EOSUSDT then.
    by_code["EOS"].update(symbol="AUSDT", history_source="binance", history_symbol="EOSUSDT")
    # Binance stopped TONUSDT on 2026-06-30 and Twelve Data has no TON.
    by_code["TON"].update(source="kraken", symbol="TONUSD", history_source="binance", history_symbol="TONUSDT")

    for code, name in STOCKS_US + STOCKS_ASIA_ADR:
        add(code, name, "stock", "twelvedata", code, live_symbol=code)
    for code, name, adr, _xetra in STOCKS_GERMAN:
        add(code, name, "stock", "adr", "", currency="EUR")
        add(adr, f"{name} ADR", "stock", "twelvedata", adr, series_of=code)

    for code, name in INDEX_ETFS:
        add(code, name, "etf_index", "twelvedata", code, live_symbol=code)

    for pair in FX_PAIRS:
        base, quote = pair.split("/")
        add(f"{base}{quote}", pair, "fx", "twelvedata", pair, currency=quote, unit=f"{quote} per {base}")

    add("XAU", "Gold", "metal", "twelvedata", "XAU/USD")
    add("XAG", "Silver", "metal", "alphavantage", "SILVER", proxy="SLV")
    add("SLV", "iShares Silver Trust", "metal", "twelvedata", "SLV", series_of="XAG", unit="share")

    add("WTI", "Crude oil (WTI)", "energy", "alphavantage", "WTI")
    add("BRENT", "Brent crude", "energy", "alphavantage", "BRENT", series_of="WTI")
    add("HEATOIL", "Heating oil", "energy", "fred", "DHOILNYH", unit="gallon")

    listed = {code: "us" for code, _ in STOCKS_US} | {code: "asia" for code, _ in STOCKS_ASIA_ADR}
    listed |= {code: "de" for code, _name, _adr, _xetra in STOCKS_GERMAN}
    for position, row in enumerate(rows, start=1):
        row["order"] = position * 10
        row["slug"] = slug_for(row)
        row["country"] = listed.get(row["code"], "")
    return rows
