"""Match an enquiry to catalogue items, without guessing.

find_matches() returns {"status": "exact" | "review" | "no_match",
"matches": [...]}, trying in order:
1. the whole enquiry is an item's name;
2. one item's full name appears inside the enquiry ("20 pcs <name>");
   several such items need review;
3. a dimension pair in the enquiry ("1 1/2 x 1" is read as 1.5 x 1) matches
   items with the same pair; if dimensions are given but nothing matches,
   no_match (never fall back to unrelated items);
4. every word of the enquiry appears in the item's name (review).
"review" and "no_match" always need a person to confirm.
"""

import re
from decimal import Decimal

REVIEW_LIMIT = 10


def normalise(text):
    """Normalise case and whitespace without removing specifications."""
    return " ".join((text or "").casefold().split())


def decimal_text(value):
    return format(Decimal(value).normalize(), "f")


def normalise_mixed_fractions(text):
    """Convert mixed fractions such as 1 1/2 to 1.5 for searching."""
    def replace(match):
        whole, numerator, denominator = (Decimal(match.group(i)) for i in (1, 2, 3))
        if denominator == 0:
            return match.group(0)
        return decimal_text(whole + numerator / denominator)
    return re.sub(r"(?<![\d/])(\d+)\s+(\d+)/(\d+)(?!\d)", replace, text)


def extract_dimension_pair(text):
    """A simple dimension pair such as 1.5 x 1, or None."""
    text = normalise_mixed_fractions(text.casefold())
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)(?!\d)", text)
    if not match:
        return None
    return decimal_text(match.group(1)), decimal_text(match.group(2))


def extract_requested_quantity(query):
    """A quantity at the start of the enquiry, e.g. "20 pcs ..." -> 20."""
    match = re.search(r"^\s*(\d+(?:\.\d+)?)\s*(?:pieces?|pcs?|sheets?|nos?|units?)\b", query, re.IGNORECASE)
    return Decimal(match.group(1)) if match else None


def find_matches(query, catalogue):
    query_norm = normalise(query)
    if not query_norm:
        return {"status": "no_match", "matches": []}

    exact = [item for item in catalogue if normalise(item["name"]) == query_norm]
    if exact:
        return {"status": "exact", "matches": exact}

    embedded = [item for item in catalogue if normalise(item["name"]) and normalise(item["name"]) in query_norm]
    if len(embedded) == 1:
        return {"status": "exact", "matches": embedded}
    if embedded:
        return {"status": "review", "matches": embedded[:REVIEW_LIMIT]}

    query_dimensions = extract_dimension_pair(query)
    if query_dimensions:
        candidates = [item for item in catalogue if extract_dimension_pair(item["name"]) == query_dimensions]
        if candidates:
            return {"status": "review", "matches": candidates[:REVIEW_LIMIT]}
        return {"status": "no_match", "matches": []}

    terms = query_norm.split()
    candidates = [item for item in catalogue if all(term in normalise(item["name"]) for term in terms)]
    if candidates:
        return {"status": "review", "matches": candidates[:REVIEW_LIMIT]}
    return {"status": "no_match", "matches": []}
