"""The data contract between sources and everything else.

A source (Lux, Tally Prime, Odoo, ERPNext, the demo data...) reads its own
system and returns one `BusinessData` dict. The dashboard, the alert email
and the insights only ever read this dict, so adding a new accounting
system means writing one source, nothing else.

Conventions every source must follow:

- Dates are `datetime.date`.
- Money is a float in the business's currency. `sales_value` and bill
  `net` include tax (what the customer paid); `sales_ex_tax`, `unit_cost`
  and purchase `taxable` are before tax. Profit is worked out before tax.
- Discounts and round-off on the whole bill are spread over its lines, so a
  bill's lines add up to its `net`.
- Returns are included with `is_return` True and negative quantity and
  money, so every total is net of returns. Returns don't count as bills.
- Cancelled documents are left out.
- `customer` is the name to show, already resolved by the source (an account
  name for credit customers, a cleaned-up typed name for cash bills), or
  None for an unnamed walk-in sale.
- `unit_cost` is the cost per unit before tax, or None when the system has
  no cost for the item (those lines are left out of profit and flagged).

`validate()` checks a dict against this contract; run it in a new source's
tests.
"""

from datetime import date
from typing import Optional, TypedDict


class Item(TypedDict):
    code: str
    name: str
    stock: float               # quantity on hand now (may be negative)
    unit_cost: Optional[float]  # cost per unit before tax, or None
    cost_source: str           # "bill" (average purchase price), "item" (item master rate) or "none"


class SalesLine(TypedDict):
    date: date
    bill_id: str               # unique per bill across the whole system
    bill_no: str               # the bill number staff see
    party_id: str              # account code or "" for cash sales
    customer: Optional[str]    # resolved name, None = walk-in
    credit: bool               # bill sold on credit
    item_code: str
    product: str
    qty: float
    sales_ex_tax: float
    sales_value: float         # including tax
    unit_cost: Optional[float]
    cost_source: str
    is_return: bool


class Bill(TypedDict):
    date: date
    bill_id: str
    party_id: str
    customer: Optional[str]
    credit: bool
    net: float                 # bill total including tax, negative for a return
    is_return: bool


class Purchase(TypedDict):
    date: date
    party_id: str
    supplier: str
    net: float                 # negative for a purchase return
    is_return: bool


class PurchaseLine(TypedDict):
    date: date
    item_code: str
    supplier: str
    taxable: float             # line value before tax
    qty: float


class Balance(TypedDict):
    party_id: str
    name: str
    balance: float             # positive: money owed (to the shop for receivables, by it for payables)


class BusinessData(TypedDict):
    items: list[Item]
    sales_lines: list[SalesLine]
    bills: list[Bill]
    purchases: list[Purchase]
    purchase_lines: list[PurchaseLine]
    receivables: list[Balance]   # credit customers
    payables: list[Balance]      # suppliers
    checked_at: object           # datetime the data was read (or the snapshot time)


class CatalogueItem(TypedDict):
    """One sellable item for quotations (see pulse_bi.quote)."""
    name: str
    ref: str                   # where it came from, e.g. an item code or spreadsheet row
    stock: Optional[object]    # Decimal quantity on hand, None if unknown
    rate: Optional[object]     # Decimal price base for the quote options, None if unknown


REQUIRED = {
    "items": Item,
    "sales_lines": SalesLine,
    "bills": Bill,
    "purchases": Purchase,
    "purchase_lines": PurchaseLine,
    "receivables": Balance,
    "payables": Balance,
}


def validate(data):
    """Raise ValueError if data doesn't follow the contract. Returns data."""
    problems = []
    for key, row_type in REQUIRED.items():
        rows = data.get(key)
        if not isinstance(rows, list):
            problems.append(f"{key}: missing or not a list")
            continue
        fields = row_type.__annotations__
        for index, row in enumerate(rows[:200]):  # a sample is enough for the shape
            missing = [name for name in fields if name not in row]
            if missing:
                problems.append(f"{key}[{index}]: missing {', '.join(missing)}")
                break
            if "date" in fields and not isinstance(row["date"], date):
                problems.append(f"{key}[{index}]: date is {type(row['date']).__name__}, not date")
                break
        if row_type in (SalesLine, Bill, Purchase):
            for index, row in enumerate(rows):
                value = row.get("qty", row.get("net"))
                if row.get("is_return") and value is not None and value > 0:
                    problems.append(f"{key}[{index}]: a return must have a negative quantity or amount")
                    break
    if problems:
        raise ValueError("Business data doesn't follow pulse_bi.model:\n  " + "\n  ".join(problems))
    return data
