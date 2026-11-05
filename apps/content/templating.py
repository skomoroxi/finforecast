"""The small template language used in templates and manual values.

    {price}                 a variable
    blank line              starts a new paragraph (or list item)
    a line with only ~~     separates alternative wordings of one paragraph
    ?flag: text             the paragraph appears only while the flag is true
    ?!flag: text            ...only while it is false
    Title :: text           the two parts of an item in a pairs field (FAQ, price factors)

A paragraph that needs a value we do not have is left out, so a page never prints a gap.
The wording is chosen by a hash of asset, date, field and paragraph: it changes daily, stays
stable within a day, and differs between pages.
"""

import re
import zlib
from dataclasses import dataclass

VAR = re.compile(r"\{([A-Za-z0-9_]+)\}")
CONDITION = re.compile(r"^\?(!?)([a-z0-9_]+):\s*")
PARAGRAPHS = re.compile(r"\n[ \t]*\n")
VARIANTS = re.compile(r"\n[ \t]*~~[ \t]*\n")


@dataclass(frozen=True)
class Block:
    flag: str | None
    negate: bool
    variants: tuple[str, ...]


def parse(text: str) -> list[Block]:
    blocks = []
    for chunk in PARAGRAPHS.split(text.replace("\r\n", "\n").strip()):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = CONDITION.match(chunk)
        flag, negate = (match.group(2), match.group(1) == "!") if match else (None, False)
        body = chunk[match.end() :] if match else chunk
        blocks.append(Block(flag, negate, tuple(v.strip() for v in VARIANTS.split(body))))
    return blocks


def names(text: str) -> tuple[set[str], set[str]]:
    """(variables, flags) a text refers to."""
    blocks = parse(text)
    variables = {v for b in blocks for variant in b.variants for v in VAR.findall(variant)}
    return variables, {b.flag for b in blocks if b.flag}


def render(text: str, values: dict, flags: dict, seed: str) -> list[str]:
    """The paragraphs that apply today, with their variables filled in."""
    out = []
    for i, block in enumerate(parse(text)):
        if block.flag and bool(flags.get(block.flag)) == block.negate:
            continue
        pick = zlib.crc32(f"{seed}|{i}".encode()) % len(block.variants)
        filled = _fill(block.variants[pick], values)
        if filled is not None:
            out.append(filled)
    return out


def _fill(text: str, values: dict) -> str | None:
    missing = False

    def replace(match):
        nonlocal missing
        value = values.get(match.group(1))
        if value is None:
            missing = True
            return ""
        return str(value)

    filled = VAR.sub(replace, text)
    if missing:
        return None
    return re.sub(r"\s+([.,;])", r"\1", re.sub(r"[ \t]+", " ", filled)).strip()
