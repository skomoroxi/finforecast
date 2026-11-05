"""Checks run on every save and CSV import (TECHNICAL-TASK §7.4)."""

from dataclasses import dataclass, field

from . import templating
from .context import FLAGS, VARIABLES, YEAR_VARIABLES
from .fields import BY_KEY, FLAG, PAIRS
from .models import Reviewer

TYPICAL_VALUE_LENGTH = 9  # a variable's rough length once filled in, for the length warning


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check(field_key: str, text: str) -> Report:
    report = Report()
    definition = BY_KEY.get(field_key)
    if definition is None:
        report.errors.append(f"unknown field {field_key}")
        return report

    if definition.kind == FLAG:
        if text.strip() not in ("0", "1"):
            report.errors.append("a visibility field takes 1 (show) or 0 (hide)")
        return report

    variables, flags = templating.names(text)
    allowed = VARIABLES | (YEAR_VARIABLES if definition.year_scope else set())
    for name in sorted(variables - allowed):
        report.errors.append(f"unknown substitution {{{name}}}")
    for name in sorted(flags - FLAGS):
        report.errors.append(f"unknown condition ?{name}")

    if definition.kind == PAIRS:
        for block in templating.parse(text):
            if any(" :: " not in variant for variant in block.variants):
                report.errors.append(f"each item needs ' :: ' between its two parts: {block.variants[0][:50]}")

    if definition.max_length:
        length = len(templating.VAR.sub("x" * TYPICAL_VALUE_LENGTH, text.strip()))
        if length > definition.max_length:
            report.warnings.append(f"about {length} characters, the limit is {definition.max_length}")
    return report


def full_check(field_key: str, text: str) -> Report:
    """`check`, plus what needs the database."""
    report = check(field_key, text)
    if field_key == "reviewer" and not Reviewer.objects.filter(name=text.strip()).exists():
        report.errors.append(f"no reviewer called {text.strip()}")
    return report
