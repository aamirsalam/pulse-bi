from decimal import Decimal

import pytest

from pulse_bi.quote.matching import extract_dimension_pair, extract_requested_quantity, find_matches
from pulse_bi.quote.pricing import options_from_config, price_options
from pulse_bi.quote.service import quote

CATALOGUE = [
    {"name": "Aluminium angle 1 1/2 x 1 in", "ref": "1", "stock": Decimal("40"), "rate": Decimal("520")},
    {"name": "Aluminium angle 1 x 1 in", "ref": "2", "stock": Decimal("-3"), "rate": Decimal("410")},
    {"name": "Steel hinge 4 in", "ref": "3", "stock": Decimal("100"), "rate": Decimal("0")},
    {"name": "Steel hinge 3 in", "ref": "4", "stock": None, "rate": Decimal("30")},
    {"name": "", "ref": "blank", "stock": Decimal("1"), "rate": Decimal("1")},
]


def test_whole_name_is_exact():
    assert find_matches("aluminium ANGLE 1 x 1 in", CATALOGUE)["status"] == "exact"


def test_name_inside_an_enquiry_is_exact():
    result = find_matches("20 pcs Aluminium angle 1 1/2 x 1 in please", CATALOGUE)
    assert result["status"] == "exact" and result["matches"][0]["ref"] == "1"


def test_blank_item_name_never_matches():
    assert all(item["ref"] != "blank" for item in find_matches("anything at all", CATALOGUE)["matches"])


def test_dimensions_match_after_reading_fractions():
    assert extract_dimension_pair("1 1/2 x 1") == ("1.5", "1")
    result = find_matches("angle 1.5x1", CATALOGUE)
    assert result["status"] == "review" and [m["ref"] for m in result["matches"]] == ["1"]


def test_unmatched_dimensions_never_fall_back():
    assert find_matches("angle 2 x 2", CATALOGUE) == {"status": "no_match", "matches": []}


def test_words_give_candidates_to_review():
    result = find_matches("steel hinge", CATALOGUE)
    assert result["status"] == "review" and len(result["matches"]) == 2


def test_requested_quantity():
    assert extract_requested_quantity("20 pcs angle") == Decimal("20")
    assert extract_requested_quantity("angle 20 pcs") is None


def test_prices_round_half_up():
    assert [p["value"] for p in price_options(Decimal("100.005"), (("a", 0), ("b", 12)))] == [Decimal("100.01"), Decimal("112.01")]


def test_markups_from_config():
    options = options_from_config({"markups": [{"label": "Trade", "percent": 5}]})
    assert options == (("Trade", 5),)
    assert options_from_config({}) == (("Base rate", 0), ("Option +12%", 12), ("Option +15%", 15))


def test_shortage_is_flagged_and_still_priced():
    product = quote("60 pcs Aluminium angle 1 1/2 x 1 in", CATALOGUE)["products"][0]
    assert product["shortage"] and product["shortage_by"] == Decimal("20") and product["prices"]


@pytest.mark.parametrize("text, issue", [
    ("Aluminium angle 1 x 1 in", "stock_issue"),   # negative stock
    ("Steel hinge 3 in", "stock_issue"),           # stock unknown
    ("Steel hinge 4 in", "price_issue"),           # rate zero
])
def test_prices_are_withheld(text, issue):
    product = quote(text, CATALOGUE)["products"][0]
    assert product[issue] and product["prices"] == []


def test_review_results_say_so():
    result = quote("steel hinge", CATALOGUE)
    assert result["needs_review"] and result["status"] == "review"
