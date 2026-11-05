"""AI drafts of the text formulas cannot produce (TECHNICAL-TASK §7.3а).

Started by an administrator, one request per asset and language, and stored as drafts that the
site never shows until someone approves them. Not runnable from a server in an unsupported region.
"""

import re

from django.conf import settings
from django.utils import timezone
from pydantic import BaseModel

from .models import Draft, Language

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
LANGUAGE_NAMES = {"en": "English", "de": "German"}
CLASS_NAMES = {
    "crypto": "a cryptocurrency",
    "stock": "a listed company's shares",
    "etf_index": "a stock market index",
    "fx": "a currency pair",
    "metal": "a precious metal",
    "energy": "an energy commodity",
}

SYSTEM = """You write short reference text for an educational website about market prices. Each asset \
page already shows live prices, statistical forecasts and technical indicators; your text explains \
what generally moves this asset, so a reader understands the numbers around it.

Write about what is specific to this asset: its business, use, supply and demand, or its market \
structure. A sentence that would fit any asset in its class adds nothing, so leave it out.

The page adds all numbers itself and they change every day, so write no figures, percentages, \
price levels, dates, years or forecasts. Describe enduring characteristics rather than recent \
events, because this text is not updated daily. State only what you are confident is true, and \
describe a contested claim as contested.

Keep a neutral, conditional tone. This is education, not advice, so do not tell readers to buy, \
sell or hold, and do not call anything a good or bad investment.

Plain sentences, no marketing language, no markdown."""

USER = """Draft the text for {name} ({code}), which is {kind}. Write in {language}.

- drivers: 4 to 5 factors that move the price. Each has a short title of a few words and one or two \
sentences of explanation.
- bull: 3 to 4 one-sentence arguments for a higher price.
- bear: 3 to 4 one-sentence arguments for a lower price.
- risks: 2 to 4 one-sentence risks specific to holding this asset."""


class Driver(BaseModel):
    title: str
    text: str


class AssetCopy(BaseModel):
    drivers: list[Driver]
    bull: list[str]
    bear: list[str]
    risks: list[str]


class DraftFailed(RuntimeError):
    pass


def request_copy(asset, language_code: str, client=None) -> AssetCopy:
    import anthropic  # the web process never needs it

    if client is None:
        if not settings.ANTHROPIC_API_KEY:
            raise DraftFailed("ANTHROPIC_API_KEY is not set")
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_config={"effort": "medium"},
        system=SYSTEM,
        messages=[
            {
                "role": "user",
                "content": USER.format(
                    name=asset.name,
                    code=asset.code,
                    kind=CLASS_NAMES[asset.asset_class.code],
                    language=LANGUAGE_NAMES[language_code],
                ),
            }
        ],
        output_format=AssetCopy,
    )
    if response.stop_reason != "end_turn" or response.parsed_output is None:
        raise DraftFailed(f"no usable draft: stop reason {response.stop_reason}")
    return response.parsed_output


def clean(text: str) -> str:
    """One line per item: a blank line or ' :: ' inside a sentence would split it in the template."""
    return re.sub(r"\s+", " ", text).replace(" :: ", ": ").replace("{", "(").replace("}", ")").strip()


def to_fields(copy: AssetCopy) -> dict[str, str]:
    return {
        "drivers": "\n\n".join(f"{clean(d.title)} :: {clean(d.text)}" for d in copy.drivers),
        "bull": "\n\n".join(clean(x) for x in copy.bull),
        "bear": "\n\n".join(clean(x) for x in copy.bear),
        "risks": "\n\n".join(clean(x) for x in copy.risks),
    }


def has_digits(text: str) -> bool:
    """A figure slipped in despite the brief: the reviewer should look at it first."""
    return bool(re.search(r"\d", text))


def draft_asset(asset, language_code: str, client=None) -> tuple[int, object, str]:
    copy = request_copy(asset, language_code, client)
    language = Language.objects.get(code=language_code)
    fields = to_fields(copy)
    for field, value in fields.items():
        Draft.objects.update_or_create(
            asset=asset, language=language, field=field, defaults={"value": value, "model_name": MODEL}
        )
    return len(fields), timezone.now().date(), MODEL
