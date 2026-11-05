"""Templates, formatting and checks. No database needed."""

from datetime import date

import pytest

from apps.content import defaults
from apps.content import formatting as fmt
from apps.content import templating as t
from apps.content.context import milestone
from apps.content.fields import BY_KEY, FIELDS
from apps.content.validation import check


def render(text, values=None, flags=None, seed="s"):
    return t.render(text, values or {}, flags or {}, seed)


def test_variables_are_filled():
    assert render("{name} is {price}.", {"name": "Gold", "price": "$1"}) == ["Gold is $1."]


def test_a_paragraph_with_a_missing_value_is_left_out():
    assert render("First.\n\nSecond {x}.", {"x": None}) == ["First."]


def test_conditions():
    text = "?up: Up.\n\n?!up: Not up."
    assert render(text, flags={"up": True}) == ["Up."]
    assert render(text, flags={"up": False}) == ["Not up."]


def test_a_condition_covers_every_variant_of_its_paragraph():
    assert render("?up: One.\n~~\nTwo.", flags={"up": False}) == []


def test_variant_is_stable_for_a_seed_and_varies_across_seeds():
    text = "One.\n~~\nTwo."
    assert render(text, seed="a") == render(text, seed="a")
    assert {render(text, seed=str(i))[0] for i in range(40)} == {"One.", "Two."}


def test_empty_values_leave_no_gaps_in_the_sentence():
    assert render("Closed at {price} {unit} .", {"price": "1.12", "unit": ""}) == ["Closed at 1.12."]


def test_names_finds_variables_and_flags():
    assert t.names("?up: {a}\n~~\n{b}\n\n{c}") == ({"a", "b", "c"}, {"up"})


def test_windows_line_endings_are_understood():
    assert render("One.\r\n\r\nTwo.") == ["One.", "Two."]


@pytest.mark.parametrize(
    ("value", "english", "german"),
    [
        (81344.4, "$81,344", "81.344 $"),
        (254.6, "$254.60", "254,60 $"),
        (1.3263, "$1.326", "1,326 $"),
        (0.0798, "$0.0798", "0,0798 $"),
        (0.00000473, "$0.00000473", "0,00000473 $"),
    ],
)
def test_money_follows_the_price_level_and_language(value, english, german):
    assert fmt.money(value, "USD", "en") == english
    assert fmt.money(value, "USD", "de") == german


def test_euro_and_other_currencies():
    assert fmt.money(60.98, "EUR", "en") == "€60.98"
    assert fmt.money(60.98, "EUR", "de") == "60,98 €"


def test_rates_have_four_decimals_and_no_sign():
    assert fmt.money(1.1224, "USD", "en", is_rate=True) == "1.1224"


def test_percent_and_dates():
    assert fmt.percent(0.0321, "en", signed=True) == "+3.21%"
    assert fmt.percent(-0.0321, "de", signed=True) == "−3,21 %"
    assert fmt.long_date(date(2026, 3, 5), "en") == "March 5, 2026"
    assert fmt.long_date(date(2026, 3, 5), "de") == "5. März 2026"


def test_milestone_is_a_round_number_well_above_today():
    assert milestone(54) == 100
    assert milestone(80504) == 200000
    assert milestone(0.00000473) == pytest.approx(0.00001)


def test_unknown_substitution_is_an_error():
    assert check("intro", "Price: {prise}.").errors == ["unknown substitution {prise}"]


def test_unknown_condition_is_an_error():
    assert check("intro", "?nope: Text.").errors == ["unknown condition ?nope"]


def test_year_variables_only_work_in_year_fields():
    assert check("intro", "{year_avg}").errors
    assert not check("year_text", "{year_avg}").errors


def test_pairs_need_a_separator():
    assert check("drivers", "No separator here.").errors
    assert not check("drivers", "Title :: Text.").errors


def test_long_title_is_a_warning_not_an_error():
    report = check("title", "x" * 70)
    assert report.warnings and not report.errors


def test_visibility_takes_one_or_zero():
    assert check("show_faq", "maybe").errors
    assert not check("show_faq", "0").errors


@pytest.mark.parametrize("class_code", list(defaults.CLASSES))
def test_default_templates_are_complete_and_valid(class_code):
    templates = defaults.templates_for(class_code)
    missing = {f.key for f in FIELDS if not f.optional} - set(templates)
    assert not missing
    for key, body in templates.items():
        assert key in BY_KEY
        assert not check(key, body).errors, key
