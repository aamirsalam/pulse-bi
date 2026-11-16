from datetime import date

import pytest

from pulse_bi.alerts import email as alerts
from pulse_bi.channels.whatsapp import handle_message
from pulse_bi.config import Customer
from pulse_bi.dashboard.publish import save_pages
from pulse_bi.web import create_app


@pytest.fixture()
def customer():
    return Customer.load("demo")


def test_whatsapp_replies_to_allowed_staff(customer):
    reply = handle_message("steel hinge", "+91 90000-00001", customer)
    assert "Steel hinge" in reply and "Draft only" in reply


def test_whatsapp_ignores_other_numbers(customer):
    assert handle_message("steel hinge", "+91 99999 99999", customer) is None
    assert handle_message("steel hinge", "", customer) is None


def test_whatsapp_can_be_switched_off(customer):
    customer.raw["channels"]["whatsapp"] = False
    assert handle_message("steel hinge", "+919000000001", customer) is None


def test_whatsapp_allow_list_starts_empty_in_the_example():
    example = Customer.load("customers/lux.example.toml")
    assert example.section("whatsapp")["allowed_senders"] == []
    assert example.channels["whatsapp"] is False


def test_web_pages(customer):
    client = create_app(customer).test_client()
    assert client.get("/").status_code == 200
    page = client.get("/?q=steel hinge")
    assert page.status_code == 200 and b"Steel hinge" in page.data
    for period in ("7d", "30d", "month", "all"):
        assert client.get(f"/dashboard?period={period}").status_code == 200


def test_web_search_can_be_switched_off(customer):
    customer.raw["channels"]["web"] = False
    client = create_app(customer).test_client()
    assert client.get("/").status_code == 404
    assert client.get("/dashboard").status_code == 200


def test_publish_saves_every_period(customer):
    site = save_pages(customer, create_app(customer))
    assert sorted(p.name for p in site.iterdir()) == ["30d.html", "7d.html", "index.html", "month.html"]
    assert "Demo Hardware" in (site / "index.html").read_text(encoding="utf-8")


def test_alert_email_dry_run(customer):
    subject, preview = alerts.run(customer, dry_run=True, today=date(2026, 11, 1))
    assert subject.startswith("Demo Hardware alerts") and preview.exists()


def test_old_bills_are_not_reported_again(demo_data):
    lines = [l for l in demo_data["sales_lines"] if not l["is_return"]]
    today = date(2027, 3, 1)  # all demo bills are over 120 days old by then
    assert alerts.new_bills(lines, {"reported": {}}, today) == set()


def test_bill_checks_find_the_sale_below_cost(customer, demo_data):
    lines = [l for l in demo_data["sales_lines"] if not l["is_return"]]
    ids = {l["bill_id"] for l in lines}
    problems = alerts.check_bills(lines, ids, customer.settings)
    # The flush door is priced below cost; one hinge bill has a mistyped rate,
    # which is both below cost and an unusual price.
    assert {row["item"] for row in problems["below_cost"]} == {"Flush door 30 x 78 in", "Steel hinge 4 in (pair)"}
    assert [row["item"] for row in problems["unusual"]] == ["Steel hinge 4 in (pair)"]
    assert problems["no_cost"]
