"""WhatsApp channel tests. Need only pulse_bi/{quote,channels,sources,engine},
customers/ and demo_data/ (the partial checkout in docs/whatsapp-integration.md)."""

import pytest

from pulse_bi.channels.whatsapp import handle_message
from pulse_bi.config import Customer


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
