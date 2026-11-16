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

        The default uses load()'s items: stock on hand, and the cost per
        unit before tax as the price base. A source whose system has a
        better price base (cost including tax, a price list) overrides this.
        """
        data = data or self.load()
        return [
            {
                "name": item["name"],
                "ref": item["code"],
                "stock": Decimal(str(item["stock"])),
                "rate": None if item["unit_cost"] is None else Decimal(str(round(item["unit_cost"], 4))),
            }
            for item in data["items"]
        ]
