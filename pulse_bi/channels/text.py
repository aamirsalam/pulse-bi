"""Plain-text rendering of a quote, for WhatsApp and other chat channels.

WhatsApp formatting: *bold*, _italic_. Messages are kept short; long review
lists are cut to max_products with a count of the rest.
"""

from ..engine.formatting import inr


def stock_text(product):
    stock = product["stock"]
    if stock is None:
        return "stock missing, check before quoting"
    if stock < 0:
        return f"stock {stock.normalize():f}, a stock error: check before quoting"
    return f"stock {stock.normalize():f}"


def render_text(result, currency="₹", max_products=5):
    if not result["query"]:
        return "Send an item name or size, e.g. *20 pcs 1 1/2 x 1 angle*."
    if result["status"] == "no_match":
        return (f"No item found for _{result['query']}_. Try the name as it appears in the stock list, "
                "or check with the shop. Nothing has been quoted.")

    lines = []
    if result["status"] == "review":
        count = len(result["products"])
        lines.append(f"*{count} possible match{'es' if count != 1 else ''}* for _{result['query']}_. "
                     "Confirm the right one before quoting:")
    else:
        lines.append(f"*Match* for _{result['query']}_:")
    if result["requested_quantity"] is not None:
        lines.append(f"Requested: {result['requested_quantity'].normalize():f}")

    for number, product in enumerate(result["products"][:max_products], 1):
        lines.append("")
        lines.append(f"{number}. *{product['name']}* ({stock_text(product)})")
        if product["shortage"]:
            lines.append(f"   Short by {product['shortage_by'].normalize():f}: confirm availability.")
        if product["price_issue"]:
            lines.append("   Price withheld: the rate is missing or zero.")
        elif product["stock_issue"]:
            lines.append("   Price withheld until the stock is checked.")
        else:
            lines.append("   " + " · ".join(f"{p['label']}: {currency}{inr(p['value'], 2)}" for p in product["prices"]))

    hidden = len(result["products"]) - max_products
    if hidden > 0:
        lines.append(f"\n…and {hidden} more. Send a more exact name.")
    lines.append("\nDraft only: check before sending to a customer.")
    return "\n".join(lines)
