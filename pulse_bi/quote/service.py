"""The quoting core: enquiry in, structured quote out. Channel-free.

The web page and WhatsApp (pulse_bi.channels) only render what quote()
returns. The safety rules live here so no channel can skip them:

- Never guess a product: "review" and "no_match" need a person to confirm;
  nothing here sends a quotation to anyone.
- Withhold prices when stock is missing or negative, or the rate is
  missing or not above zero.
- Flag a shortage when the requested quantity is more than the stock.
"""

import time

from .matching import extract_requested_quantity, find_matches
from .pricing import DEFAULT_OPTIONS, price_options


def price_item(item, requested_quantity=None, options=DEFAULT_OPTIONS):
    stock = item.get("stock")
    rate = item.get("rate")
    product = {
        "name": item["name"],
        "ref": item.get("ref", ""),
        "stock": stock,
        "stock_issue": stock is None or stock < 0,
        "shortage": False,
        "shortage_by": None,
        "price_issue": rate is None or rate <= 0,
        "prices": [],
    }
    if stock is not None and stock >= 0 and requested_quantity is not None and requested_quantity > stock:
        product["shortage"] = True
        product["shortage_by"] = requested_quantity - stock
    if not product["stock_issue"] and not product["price_issue"]:
        product["prices"] = price_options(rate, options)
    return product


def quote(text, catalogue, options=DEFAULT_OPTIONS, requested_quantity=None):
    """requested_quantity overrides a quantity read from the text (e.g. one
    the enquiry parser found elsewhere in the message)."""
    query = (text or "").strip()
    result = find_matches(query, catalogue) if query else {"status": "no_match", "matches": []}
    requested = requested_quantity if requested_quantity is not None else extract_requested_quantity(query)
    return {
        "query": query,
        "status": result["status"],
        "needs_review": result["status"] != "exact",
        "requested_quantity": requested,
        "products": [price_item(item, requested, options) for item in result["matches"]],
    }


class Quoter:
    """Quotes for one customer, keeping the catalogue for cache_seconds so a
    busy WhatsApp number doesn't re-read the accounts system per message."""

    def __init__(self, source, options=DEFAULT_OPTIONS, cache_seconds=300):
        self.source = source
        self.options = options
        self.cache_seconds = cache_seconds
        self._catalogue = None
        self._loaded_at = 0.0

    def catalogue(self):
        if self._catalogue is None or time.monotonic() - self._loaded_at > self.cache_seconds:
            self._catalogue = self.source.load_catalogue()
            self._loaded_at = time.monotonic()
        return self._catalogue

    def quote(self, text, requested_quantity=None):
        return quote(text, self.catalogue(), self.options, requested_quantity)
