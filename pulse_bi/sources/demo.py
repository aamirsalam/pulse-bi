"""Demo source: CSV files laid out like the BusinessData contract.

Used for development, tests and demos without a customer's real data, and
as a template for importing from any system that can export spreadsheets.
One CSV per BusinessData list, named after it (items.csv, sales_lines.csv,
bills.csv, purchases.csv, purchase_lines.csv, receivables.csv,
payables.csv), with the contract's field names as headers. Dates are
YYYY-MM-DD; blank unit_cost / customer mean None.

[source]
type = "demo"
path = "demo_data"       # folder with the CSVs, relative to the repo
"""

import csv
from datetime import date, datetime
from pathlib import Path

from ..model import REQUIRED, validate
from .base import Source

REPO = Path(__file__).resolve().parents[2]


def convert(field, kind, value):
    if kind is date:
        return date.fromisoformat(value)
    if kind is bool:
        return value.strip().lower() in ("1", "true", "yes", "y")
    if kind is float:
        return float(value or 0)
    if "Optional[float]" in str(kind) or kind == (float | None):
        return float(value) if value.strip() else None
    if "Optional[str]" in str(kind):
        return value.strip() or None
    return value


class DemoSource(Source):
    label = "demo data"

    def __init__(self, config, settings=None):
        super().__init__(config, settings)
        path = Path(config.get("path", "demo_data"))
        self.folder = path if path.is_absolute() else REPO / path

    def load(self):
        data = {}
        for name, row_type in REQUIRED.items():
            fields = row_type.__annotations__
            with open(self.folder / f"{name}.csv", newline="", encoding="utf-8") as file:
                data[name] = [
                    {field: convert(field, fields[field], row[field]) for field in fields}
                    for row in csv.DictReader(file)
                ]
        data["checked_at"] = datetime.fromtimestamp((self.folder / "bills.csv").stat().st_mtime).astimezone()
        return validate(data)
