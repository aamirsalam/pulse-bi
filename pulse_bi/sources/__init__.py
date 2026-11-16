"""Data sources, picked per customer by [source] type in the config.

    lux      LUX accounting (Access .mdb)             working
    demo     CSV files in the BusinessData shape      working (made-up data in demo_data/)
    tally    Tally Prime                              not written yet
    odoo     Odoo                                     not written yet
    erpnext  ERPNext / Frappe                         not written yet
"""

from importlib import import_module

SOURCES = {
    "lux": "pulse_bi.sources.lux:LuxSource",
    "demo": "pulse_bi.sources.demo:DemoSource",
    "tally": "pulse_bi.sources.tally:TallySource",
    "odoo": "pulse_bi.sources.odoo:OdooSource",
    "erpnext": "pulse_bi.sources.erpnext:ERPNextSource",
}


def build_source(config):
    """The source for a customer's [source] table."""
    kind = config.get("type")
    if kind not in SOURCES:
        raise ValueError(f"Unknown source type {kind!r}; choose one of: {', '.join(SOURCES)}")
    module_name, class_name = SOURCES[kind].split(":")
    return getattr(import_module(module_name), class_name)(config)
