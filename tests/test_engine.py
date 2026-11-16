from datetime import date, timedelta

import pytest

from pulse_bi.engine import insights as E


@pytest.fixture(scope="module")
def latest(demo_data):
    return E.latest_date(demo_data)


def test_returns_come_off_sales_but_are_not_bills(demo_data):
    returns = [bill for bill in demo_data["bills"] if bill["is_return"]]
    assert returns
    summary = E.sales_summary(demo_data["bills"])
    assert summary["sales_invoice_count"] == len(demo_data["bills"]) - len(returns)
    assert summary["sales_net_amount"] == pytest.approx(sum(bill["net"] for bill in demo_data["bills"]))


def test_period_figures(demo_data, latest):
    week = E.build_insights("7d", demo_data)["comparison"]
    assert week["start"] == latest - timedelta(days=6)
    assert week["end"] == latest
    bills = [b for b in demo_data["bills"] if b["date"] >= week["start"] and not b["is_return"]]
    assert week["current"]["invoices"] == len(bills)
    assert week["change"]["net_sales"] is not None


def test_first_month_has_no_full_previous_period(demo_data):
    first = min(bill["date"] for bill in demo_data["bills"])
    comparison = E.period_comparison(demo_data["bills"], demo_data["sales_lines"], "30d", first + timedelta(days=40))
    assert comparison["previous_partial"] and comparison["change"] == {}


def test_sale_below_cost_is_flagged(demo_data):
    loss = E.build_insights("all", demo_data)["margins"]["loss_items"]
    assert [item["code"] for item in loss] == ["D202"]


def test_margin_checks_can_ignore_early_bills(demo_data):
    settings = E.Settings(margin_ignore_before=date(2027, 1, 1))
    margins = E.build_insights("all", demo_data, settings)["margins"]
    assert margins["loss_items"] == [] and margins["ignored_before"] == date(2027, 1, 1)


def test_stock_not_moving(demo_data):
    dead = E.build_insights("all", demo_data)["stock"]["dead_items"]
    assert {item["code"] for item in dead} == {"S402", "L801"}


def test_out_of_stock_items_come_first_in_reorder(demo_data):
    reorder = E.build_insights("all", demo_data)["reorder"]["items"]
    out = [a for a in reorder if a["stock"] <= 0]
    assert out and reorder[: len(out)] == out
    assert all(a["suggested"] > 0 for a in reorder)


def test_item_without_cost_is_left_out_of_profit(demo_data):
    profit = E.summarise_profit(demo_data["sales_lines"])
    assert profit["profit_missing_lines"] == sum(1 for l in demo_data["sales_lines"] if l["item_code"] == "M601")


def test_money_owed_is_aged(demo_data):
    receivables = E.build_insights("all", demo_data)["receivables"]
    owed = sum(row["balance"] for row in demo_data["receivables"] if row["balance"] >= 1)
    assert receivables["total"] == pytest.approx(owed)
    assert sum(b["amount"] for b in receivables["buckets"]) == pytest.approx(owed)


def test_walk_ins_are_kept_apart(demo_data):
    customers = E.build_insights("all", demo_data)["customers"]
    assert customers["walk_in_sales"] > 0
    assert all(c["name"] != E.WALK_IN for c in customers["top"])


def test_settings_from_config():
    settings = E.Settings.from_config({"low_margin_percent": 12, "margin_ignore_before": "2026-09-26", "unknown": 1})
    assert settings.low_margin_percent == 12
    assert settings.margin_ignore_before == date(2026, 9, 26)
