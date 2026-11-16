"""Catalogue from a stock report CSV (made by tools/import_stock_report.py).

Columns used: ItemName, Closing (stock), P/Rate+Tax (the price base) and
SourceRow (the row in the original spreadsheet).
"""

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def to_decimal(value):
    try:
        text = str(value or "").replace(",", "").strip()
        if not text:
            return None
        number = Decimal(text)
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def load_stock_report_csv(path):
    path = Path(path)
    path = path if path.is_absolute() else REPO / path
    if not path.exists():
        raise FileNotFoundError(f"Stock report CSV not found: {path} (run tools/import_stock_report.py)")
    with path.open(newline="", encoding="utf-8-sig") as file:
        return [
            {
                "name": row.get("ItemName") or "Unnamed product",
                "ref": f"row {row.get('SourceRow', '?')}",
                "stock": to_decimal(row.get("Closing")),
                "rate": to_decimal(row.get("P/Rate+Tax")),
            }
            for row in csv.DictReader(file)
        ]
