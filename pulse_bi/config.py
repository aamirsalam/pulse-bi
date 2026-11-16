"""Per-customer settings: one TOML file per customer in customers/.

customers/demo.toml runs on the made-up demo data; copy
customers/lux.example.toml (or demo.toml) to customers/<name>.toml for a real
customer. Real customer files are git-ignored: they hold paths and phone
numbers. Secrets (passwords, API keys, app passwords) never go in these
files, only in environment variables.

Pick a customer with --customer <name or path>, or PULSE_CUSTOMER.
"""

import os
import tomllib
from functools import cached_property
from pathlib import Path

from .engine.insights import Settings
from .quote.pricing import options_from_config

REPO = Path(__file__).resolve().parents[1]
CUSTOMERS = REPO / "customers"


def find_config(name=None):
    name = name or os.environ.get("PULSE_CUSTOMER") or "demo"
    path = Path(name)
    if path.suffix != ".toml":
        path = CUSTOMERS / f"{name}.toml"
    elif not path.is_absolute() and not path.exists():
        path = REPO / path
    if not path.exists():
        raise FileNotFoundError(f"No customer config at {path}")
    return path


class Customer:
    def __init__(self, raw, path=None):
        self.raw = raw
        self.path = path
        self.slug = raw.get("slug") or (path.stem if path else "customer")
        self.business_name = raw.get("business", {}).get("name", self.slug)
        self.currency_symbol = raw.get("business", {}).get("currency_symbol", "₹")
        self.tax_name = raw.get("business", {}).get("tax_name", "GST")

    @classmethod
    def load(cls, name=None):
        path = find_config(name)
        with path.open("rb") as file:
            return cls(tomllib.load(file), path)

    def section(self, name):
        return self.raw.get(name, {})

    @cached_property
    def source(self):
        from .sources import build_source
        return build_source(self.section("source"))

    @cached_property
    def settings(self):
        return Settings.from_config(self.section("insights"))

    @property
    def channels(self):
        """Enabled front ends for quotes, e.g. {"web": True, "whatsapp": False}."""
        return {"web": True, "whatsapp": False, **self.section("channels")}

    @property
    def dashboard(self):
        return {"local": True, **self.section("dashboard")}

    @cached_property
    def quoter(self):
        from .quote.service import Quoter
        quote = self.section("quote")
        return Quoter(self.source, options_from_config(quote), quote.get("cache_seconds", 300))

    def output_dir(self, *parts):
        path = REPO / "output" / self.slug
        for part in parts:
            path = path / part
        return path
