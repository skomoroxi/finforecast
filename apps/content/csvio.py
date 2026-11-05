"""CSV export and import (TECHNICAL-TASK §7.4). Imports pass the same checks as a manual save."""

import csv
import io
from dataclasses import dataclass, field

from apps.market.models import Asset, AssetClass

from . import services, validation
from .models import Language, Override, Template

OVERRIDE_COLUMNS = ["asset", "language", "field", "value"]
TEMPLATE_COLUMNS = ["class", "language", "field", "template"]


@dataclass
class ImportReport:
    saved: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def export_overrides() -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(OVERRIDE_COLUMNS)
    for o in Override.objects.select_related("asset", "language"):
        writer.writerow([o.asset.code, o.language.code, o.field, o.value])
    return out.getvalue()


def export_templates() -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(TEMPLATE_COLUMNS)
    for t in Template.objects.select_related("asset_class", "language"):
        writer.writerow([t.asset_class.code, t.language.code, t.field, t.body])
    return out.getvalue()


def _rows(text: str, columns: list[str], report: ImportReport):
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if reader.fieldnames != columns:
        report.errors.append(f"expected the columns {', '.join(columns)}")
        return
    yield from enumerate(reader, start=2)


def _checked(line: int, field_key: str, value: str, report: ImportReport) -> bool:
    result = validation.check(field_key, value)
    report.warnings += [f"line {line}: {w}" for w in result.warnings]
    report.errors += [f"line {line}: {e}" for e in result.errors]
    return not result.errors


def import_overrides(text: str, user=None) -> ImportReport:
    report = ImportReport()
    assets = {a.code: a for a in Asset.objects.all()}
    languages = {x.code: x for x in Language.objects.all()}
    for line, row in _rows(text, OVERRIDE_COLUMNS, report):
        asset, language = assets.get(row["asset"]), languages.get(row["language"])
        if asset is None or language is None:
            report.errors.append(f"line {line}: unknown asset or language")
        elif _checked(line, row["field"], row["value"], report):
            services.save_override(asset, language, row["field"], row["value"], user, "CSV import")
            report.saved += 1
    return report


def import_templates(text: str, user=None) -> ImportReport:
    report = ImportReport()
    classes = {c.code: c for c in AssetClass.objects.all()}
    languages = {x.code: x for x in Language.objects.all()}
    for line, row in _rows(text, TEMPLATE_COLUMNS, report):
        asset_class, language = classes.get(row["class"]), languages.get(row["language"])
        if asset_class is None or language is None:
            report.errors.append(f"line {line}: unknown class or language")
        elif _checked(line, row["field"], row["template"], report):
            services.save_template(asset_class, language, row["field"], row["template"], user, "CSV import")
            report.saved += 1
    return report
