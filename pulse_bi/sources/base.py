"""What every data source provides.

A source is picked per customer by `[source] type` in customers/<name>.toml
(see pulse_bi/sources/__init__.py for the list). To add a system, subclass
Source, fill load() with a BusinessData dict (pulse_bi.model) and register
it in SOURCES.
"""

from decimal import Decimal


class SourceNotReady(NotImplementedError):
    """Raised by sources that are documented but not written yet."""


class Source:
    #: Shown on the dashboard, e.g. "Live from Tally Prime".
    label = "the accounts system"

    def __init__(self, config, settings=None):
        """config is the [source] table of the customer's config."""
        self.config = config

    def load(self):
        """Read the system and return a BusinessData dict (pulse_bi.model)."""
        raise NotImplementedError

    def load_catalogue(self, data=None):
        """Sellable items for quotations: a list of pulse_bi.model.CatalogueItem.

        The quote's options are the rate plus markups, so the rate must be
        the item's cost INCLUDING tax (or a price list's base price). The
        contract's unit_cost is before tax, so it can't be used as is: +12%
        on a cost before 18% GST quotes below the real cost. By default the
        rate is None, which withholds prices; a source sets it from its
        system's tax-inclusive cost or price list (see DemoSource and the
        LUX stock report CSV).
        """
        data = data or self.load()
        return [
            {"name": item["name"], "ref": item["code"], "stock": Decimal(str(item["stock"])), "rate": None}
            for item in data["items"]
        ]
