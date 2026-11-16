
"""Turn a LUX stock report export (.xlsx) into the CSV that quotations read.

    python tools/import_stock_report.py <stock_report.xlsx> [data/inventory_import.csv]

The export has its headers on row 6 of Sheet2 and data from row 7; the
column list is checked exactly, so a changed report layout stops here
instead of producing wrong prices. Point [source] catalogue_csv in the
customer config at the output. Needs openpyxl.
"""

import csv
import sys
from pathlib import Path

from openpyxl import load_workbook

REPO = Path(__file__).resolve().parents[1]
if len(sys.argv) < 2:
    sys.exit(__doc__)
SOURCE_FILE = Path(sys.argv[1])
OUTPUT_FILE = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / "data" / "inventory_import.csv"
OUTPUT_DIR = OUTPUT_FILE.parent

EXPECTED_HEADERS = [
    "ItemName",
    "Op.Stock",
    "Purchase",
    "Sales",
    "SalesRtn",
    "Prch.Rtn",
    "Production",
    "Consumption",
    "Closing",
    "P/Rate+Tax",
    "P/Rate",
    "StkValue",
]


def main():
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            f"Stock report not found: {SOURCE_FILE}"
        )

    workbook = load_workbook(
        SOURCE_FILE,
        read_only=True,
        data_only=True,
    )

    try:
        sheet = workbook["Sheet2"]

        # The exported report has its column headers on row 6.
        headers = [
            str(value).strip() if value is not None else ""
            for value in next(
                sheet.iter_rows(
                    min_row=6,
                    max_row=6,
                    max_col=12,
                    values_only=True,
                )
            )
        ]

        if headers != EXPECTED_HEADERS:
            raise ValueError(
                "Unexpected stock report columns.\n"
                f"Expected: {EXPECTED_HEADERS}\n"
                f"Found:    {headers}"
            )

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        imported = 0
        skipped_empty = 0

        with OUTPUT_FILE.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=["SourceRow"] + EXPECTED_HEADERS,
            )
            writer.writeheader()

            # Data begins on Excel row 7.
            for excel_row, values in enumerate(
                sheet.iter_rows(
                    min_row=7,
                    max_col=12,
                    values_only=True,
                ),
                start=7,
            ):
                record = dict(zip(EXPECTED_HEADERS, values))

                # Skip report padding and rows without an item name.
                if record["ItemName"] is None or not str(
                    record["ItemName"]
                ).strip():
                    skipped_empty += 1
                    continue

                # Preserve the original item description and source row.
                writer.writerow({
                    "SourceRow": excel_row,
                    **record,
                })
                imported += 1

    finally:
        workbook.close()

    print("Inventory import completed.")
    print(f"Source:  {SOURCE_FILE.name}")
    print(f"Output:  {OUTPUT_FILE}")
    print(f"Imported item rows: {imported}")
    print(f"Empty rows skipped: {skipped_empty}")
    print("No deduplication or price changes were performed.")


if __name__ == "__main__":
    main()
