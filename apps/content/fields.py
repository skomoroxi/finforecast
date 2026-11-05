"""Every editable field of an asset page (TECHNICAL-TASK §7.2)."""

from dataclasses import dataclass

LINE, TEXT, LIST, PAIRS, FLAG = "line", "text", "list", "pairs", "flag"


@dataclass(frozen=True)
class Field:
    key: str
    kind: str
    section: str
    label: str
    max_length: int | None = None
    optional: bool = False  # no default template needed
    year_scope: bool = False  # rendered once per calendar year, can use the year variables


HEADINGS = [
    ("h_summary", "Summary"),
    ("h_chart", "Chart"),
    ("h_next30", "30 days"),
    ("h_tomorrow", "Tomorrow"),
    ("h_this_year", "Current year"),
    ("h_five_years", "Next 5 years"),
    ("h_outlook", "Long-term outlook"),
    ("h_ta", "Technical analysis"),
    ("h_analysts", "Analysts"),
    ("h_drivers", "Price factors"),
    ("h_history", "Price history"),
    ("h_investment", "Is it a good investment"),
    ("h_accuracy", "Method and accuracy"),
    ("h_faq", "FAQ"),
]
SECTIONS = [
    "summary",
    "chart",
    "next30",
    "tomorrow",
    "this_year",
    "five_years",
    "outlook",
    "ta",
    "analysts",
    "drivers",
    "history",
    "investment",
    "accuracy",
    "faq",
]

FIELDS = [
    Field("title", LINE, "seo", "Title", max_length=60),
    Field("meta_description", LINE, "seo", "Meta description", max_length=160),
    Field("h1", LINE, "seo", "H1"),
    *[Field(key, LINE, "headings", label) for key, label in HEADINGS],
    Field("h_year", LINE, "headings", "Year heading", year_scope=True),
    Field("intro", TEXT, "text", "Intro"),
    Field("summary", TEXT, "text", "Summary"),
    Field("price_note", TEXT, "text", "Note on the price", optional=True),
    Field("next30", TEXT, "text", "30-day text"),
    Field("year_text", TEXT, "text", "Text for each year", year_scope=True),
    Field("outlook", TEXT, "text", "Long-term text"),
    Field("technical", TEXT, "text", "Technical analysis text"),
    Field("accuracy", TEXT, "text", "Accuracy text"),
    Field("drivers", PAIRS, "lists", "Price factors"),
    Field("bull", LIST, "lists", "Arguments for"),
    Field("bear", LIST, "lists", "Arguments against"),
    Field("risks", LIST, "lists", "Risks"),
    Field("faq", PAIRS, "lists", "FAQ"),
    Field("reviewer", LINE, "other", "Author or reviewer"),
    Field("hero_image", LINE, "other", "Main image", optional=True),
    *[Field(f"show_{s}", FLAG, "visibility", f"Show section: {s}", optional=True) for s in SECTIONS],
]
BY_KEY = {f.key: f for f in FIELDS}
