"""Optional: pull items out of a free-text enquiry with a local AI model.

Customers write things like "20 sheet venam, 8 adi x 4 adi, 2 mm" (English,
Manglish or Hinglish). parse_enquiry() asks a local Ollama model for a JSON
list of items, then trusts plain regular expressions over the model for the
clear patterns: a feet x feet size ("8 adi x 4 adi") and a leading quantity
("20 sheets"). Each item's product text can then go to pulse_bi.quote.

Off unless the customer config turns it on; nothing in the channels calls it
yet. The WhatsApp integration can use it for messages that don't match an
item name directly, then quote each item (see request_flow() for the order
the original tool used). Needs Ollama running with the model pulled.

[quote.llm]
enabled = true
url = "http://localhost:11434/api/chat"
model = "qwen3:1.7b"
"""

import json
import re
import urllib.request
from decimal import Decimal

DEFAULT_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen3:1.7b"
GENERIC_TERMS = {"angle", "sheet", "pipe", "profile", "square"}


def extract_feet_dimensions(message):
    """(length, width, "feet") for "8 adi x 4 adi", "8 ft by 4 ft"..., or None."""
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:adi|feet|foot|ft)\s*(?:x|×|by)\s*(\d+(?:\.\d+)?)\s*(?:adi|feet|foot|ft)",
        message.casefold(),
    )
    return (float(match.group(1)), float(match.group(2)), "feet") if match else None


def extract_leading_quantity(message):
    """(quantity, "sheets" | "pieces") for "20 sheets ...", or None."""
    match = re.search(r"^\s*(\d+(?:\.\d+)?)\s+(sheets?|pieces?|pcs?)\b", message, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1)), "sheets" if match.group(2).casefold().startswith("sheet") else "pieces"


def apply_overrides(message, parsed):
    """Correct the model's first item with the clear patterns in the message,
    and refuse quantities that aren't above zero. Returns parsed."""
    if not isinstance(parsed.get("items"), list):
        raise ValueError("Model response must contain an items list.")
    items = parsed["items"]
    dimensions = extract_feet_dimensions(message)
    if dimensions and items:
        items[0]["length"], items[0]["width"], items[0]["dimension_unit"] = dimensions
    quantity = extract_leading_quantity(message)
    if quantity and items:
        items[0]["quantity"], items[0]["quantity_unit"] = quantity
    for item in items:
        if item.get("quantity") is not None and item["quantity"] <= 0:
            raise ValueError("Quantity must be greater than zero.")
    return parsed


def parse_enquiry(message, url=DEFAULT_URL, model=DEFAULT_MODEL, timeout=120):
    """Items requested in a free-text enquiry: {"items": [{"product", "quantity", ...}]}."""
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "product": {"type": ["string", "null"]},
                        "length": {"type": ["number", "null"]},
                        "width": {"type": ["number", "null"]},
                        "dimension_unit": {"type": ["string", "null"]},
                        "thickness": {"type": ["number", "null"]},
                        "thickness_unit": {"type": ["string", "null"]},
                        "quantity": {"type": ["number", "null"]},
                        "quantity_unit": {"type": ["string", "null"]},
                    },
                    "required": [
                        "product",
                        "length",
                        "width",
                        "dimension_unit",
                        "thickness",
                        "thickness_unit",
                        "quantity",
                        "quantity_unit",
                    ],
                },
            }
        },
        "required": ["items"],
    }

    payload = {
        "model": model,
        "stream": False,
        "format": schema,
        "think": False,
        "messages": [
            {
                "role": "system",
                "content": (
                            "Extract one item per distinct product requested. "
                            "Understand English, Malayalam written in Latin letters (Manglish), "
                            "and Hindi written in Latin letters (Hinglish). "
                            "Words such as 'venam' mean 'want/need', 'adi' means feet, "
                            "'chahiye' means 'want/need', and 'mota' can describe thickness. "
                            "These words are request language, not product names. "
                            "Do not include quantities or request words in the product description. "
                            "Do not split one product request into multiple items just because "
                            "the message contains dimensions or specifications. "
                            "Extract only details explicitly stated; never invent missing values. "
                            "Use null for missing values. "
                            "Keep dimension units separate from thickness units. "
                            "If dimensions are given as '8 adi 4 adi', interpret them as "
                            "length 8 and width 4, with dimension_unit 'feet'. "
                            "If length and width are both null, dimension_unit must be null. "
                            "Never use a thickness unit as a dimension unit unless explicitly stated. "
                            "Preserve the material and product type in the product description. "
                            "For quantity_unit, use the stated unit, such as 'sheets', 'pieces', "
                            "'lengths', or 'kg'. If no unit is stated, use null. "
                            "Return an empty items array only if no product request is present."


                ),
            },
            {"role": "user", "content": message},
        ],
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    return apply_overrides(message, json.loads(result["message"]["content"]))


def search_text(item, message):
    """What to search for: the model's product text, or the whole message
    when the model only returned a generic word like "sheet"."""
    product = (item.get("product") or "").strip()
    return message if product.casefold() in GENERIC_TERMS else product


def request_flow(message, quoter, llm_config):
    """The original tool's order: quote the message directly if it contains
    an exact item name; otherwise ask the model for the items and quote
    each. Returns a list of quote results."""
    direct = quoter.quote(message)
    if direct["status"] == "exact" or not llm_config.get("enabled"):
        return [direct]
    parsed = parse_enquiry(message, llm_config.get("url", DEFAULT_URL), llm_config.get("model", DEFAULT_MODEL))
    return [
        quoter.quote(search_text(item, message),
                     None if item.get("quantity") is None else Decimal(str(item["quantity"])))
        for item in parsed["items"] if item.get("product")
    ]
