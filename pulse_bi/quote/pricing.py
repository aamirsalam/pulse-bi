"""Price options for a quote.

Each option is the item's rate times (1 + markup %), rounded half-up to two
decimals with Decimal. The markups are per customer ([quote] markups in the
config); the default is the rate itself, +12% and +15%.
"""

from decimal import Decimal, ROUND_HALF_UP

DEFAULT_OPTIONS = (("Base rate", 0), ("Option +12%", 12), ("Option +15%", 15))


def money(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def price_options(rate, options=DEFAULT_OPTIONS):
    """[{"label", "value"}] for a Decimal rate. rate must be finite and > 0."""
    return [
        {"label": label, "value": money(rate * (Decimal(1) + Decimal(str(markup)) / 100))}
        for label, markup in options
    ]


def options_from_config(section):
    """[quote] markups = [{label = "...", percent = 12}, ...] -> options."""
    markups = (section or {}).get("markups")
    if not markups:
        return DEFAULT_OPTIONS
    return tuple((entry["label"], entry["percent"]) for entry in markups)
