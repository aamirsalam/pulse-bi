"""WhatsApp channel: the hand-off point for the WhatsApp integration.

The integration (webhook, Meta's WhatsApp Business API or a provider,
sending replies) is built around one call:

    reply = handle_message(text, sender, customer)
    if reply:
        send_whatsapp_text(sender, reply)   # the integration's own function

handle_message() returns None when the message should get no reply: the
WhatsApp channel is switched off for this customer, or the sender isn't on
the allow-list.

Staff only, by default. A quote shows the base rate (the cost-based price)
and "possible match" guesses that a person must confirm, so it must not go
straight to customers. [whatsapp] allowed_senders in the customer config
lists the staff numbers allowed to ask; it starts empty, so nobody gets a
reply until numbers are added. Changing that to answer customers directly
is a business decision, not a config tweak: it needs a customer-safe reply
(no cost-based price, no guesses).

[channels]
whatsapp = true

[whatsapp]
allowed_senders = ["+91 98xxxxxxxx"]   # any format; only the digits are compared
max_products = 5
"""

import re

from .text import render_text


def digits(number):
    return re.sub(r"\D", "", str(number or ""))


def allowed(sender, customer):
    numbers = {digits(n) for n in customer.section("whatsapp").get("allowed_senders", [])}
    return bool(digits(sender)) and digits(sender) in numbers


def handle_message(text, sender, customer):
    """The reply text for an incoming WhatsApp message, or None for no reply."""
    if not customer.channels.get("whatsapp") or not allowed(sender, customer):
        return None
    result = customer.quoter.quote(text)
    return render_text(
        result,
        currency=customer.currency_symbol,
        max_products=customer.section("whatsapp").get("max_products", 5),
    )
