import copy
from datetime import date

import pytest

from pulse_bi.model import validate
from pulse_bi.sources import SOURCES, build_source
from pulse_bi.sources.base import SourceNotReady
from pulse_bi.sources.lux.source import apply_bill_adjustment, tidy_typed_name


def test_demo_data_follows_the_contract(demo_data):
    validate(demo_data)
    assert all(isinstance(line["date"], date) for line in demo_data["sales_lines"])


def test_bills_add_up_to_their_lines(demo_data):
    totals = {}
    for line in demo_data["sales_lines"]:
        totals[line["bill_id"]] = totals.get(line["bill_id"], 0) + line["sales_value"]
    for bill in demo_data["bills"]:
        assert totals[bill["bill_id"]] == pytest.approx(bill["net"], abs=0.05)


def test_validate_catches_a_missing_field(demo_data):
    broken = copy.deepcopy(demo_data)
    del broken["items"][0]["unit_cost"]
    with pytest.raises(ValueError, match="items"):
        validate(broken)


def test_validate_catches_a_positive_return(demo_data):
    broken = copy.deepcopy(demo_data)
    line = next(line for line in broken["sales_lines"] if line["is_return"])
    line["qty"] = abs(line["qty"])
    with pytest.raises(ValueError, match="return"):
        validate(broken)


@pytest.mark.parametrize("kind", ["tally", "odoo", "erpnext"])
def test_unwritten_sources_say_so(kind):
    with pytest.raises(SourceNotReady):
        build_source({"type": kind}).load()


def test_unknown_source_is_refused():
    with pytest.raises(ValueError, match="Unknown source"):
        build_source({"type": "quickbooks"})


def test_every_registered_source_can_be_built():
    for kind in SOURCES:
        build_source({"type": kind, "path": "demo_data"})


@pytest.mark.parametrize("typed, expected", [
    ("JOHNcal Sales", "JOHN"),
    ("MARYales", "MARY"),
    ("Local Sales", None),
    ("cash", None),
    ("ANIL-gpay", "ANIL"),
    ("RAVI 9876543210", "RAVI"),
    ("", None),
])
def test_lux_typed_names_are_tidied(typed, expected):
    assert tidy_typed_name(typed) == expected


def test_lux_bill_discount_is_spread_over_the_lines():
    lines = [{"sales_value": 1180.0, "sales_ex_tax": 1000.0}, {"sales_value": 118.0, "sales_ex_tax": 100.0}]
    apply_bill_adjustment(1250.0, lines)
    assert sum(line["sales_value"] for line in lines) == pytest.approx(1250.0)
    assert lines[0]["sales_ex_tax"] / lines[1]["sales_ex_tax"] == pytest.approx(10)


def test_lux_bill_far_from_its_lines_is_left_alone():
    lines = [{"sales_value": 1000.0, "sales_ex_tax": 850.0}]
    apply_bill_adjustment(100.0, lines)
    assert lines[0]["sales_value"] == 1000.0
