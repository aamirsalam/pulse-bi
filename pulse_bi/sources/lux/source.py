"""LUX accounting software (a Microsoft Access .mdb file).

All the LUX-specific knowledge lives here; everything after load() only
sees a BusinessData dict (pulse_bi.model).

Reading the file:
- On Windows, through pyodbc and the Microsoft Access ODBC driver
  (`database` in the config). Access SQL: IIF, Trim, parenthesised joins.
- Anywhere else, from a SQLite copy made with mdbtools (`sqlite` in the
  config; see sqlite_copy.py, which makes the copy and mimics pyodbc rows).

How LUX keeps its books (learned the hard way):
- Stock is opening stock + purchases - sales - purchase returns + sales
  returns over the item master, as LUX's own Stock Report does. Don't read
  StockRegisterP (only rebuilt when staff open the Stock Report) or
  ItemMaster.ClosingStock (adjusted on each save, drifts).
- Child rows join their master on InvoiceNo AND Trim(FormNo); InvoiceNo
  alone isn't unique.
- TaxPerc/TaxAmt on bill lines are only the CGST half, so a line's value
  including GST is TaxableAmt + 2 * TaxAmt + IGSTAmount. Discounts and
  round-off on the whole bill aren't on the lines, so each bill's lines
  are scaled to its NetAmount.
- Cost is the item's average purchase-bill rate before GST
  (PurchaseChild.TaxableAmt / Totalqty), falling back to ItemMaster.PurchRate.
  The with-tax rates (InvoiceChild.PRate, ItemMaster.PRateWithTax) are
  calculated by LUX and can be wrong for merged items.
- Credit customers are Account rows in the Sundry Debtors group, suppliers
  in Sundry Creditors (group ids in the config). Account.Cl_Bal isn't kept
  up to date, so a balance is op_bal (sign from Op_Crdr) + Dr - Cr over
  AccTransChld.
- Cash bills all go to one cash-sales account; the customer is only the
  name typed on the bill (InvoiceMaster.cname), which staff often type over
  LUX's default text, so it's cleaned up by tidy_typed_name().
- LUX starts a new .mdb each financial year (e.g. 2026-27.mdb); point
  `database` at the current one.
"""

import os
import re
from collections import defaultdict
from datetime import datetime

from ..base import Source

NOT_CANCELLED = "Cancelled <> 'Y'"

# (child table, master table, effect on stock)
STOCK_MOVEMENTS = (
    ("PurchaseChild", "purchasemaster", 1),
    ("InvoiceChild", "InvoiceMaster", -1),
    ("PurchaseReturnChild", "PurchaseReturnMaster", -1),
    ("InvoiceReturnChild", "InvoiceReturnMaster", 1),
)

# (child table, master table, sign): sales bills, and sales returns, which
# become lines with negative quantity and value.
SALES_TABLES = (
    ("InvoiceChild", "InvoiceMaster", 1),
    ("InvoiceReturnChild", "InvoiceReturnMaster", -1),
)


def as_date(value):
    return value.date() if isinstance(value, datetime) else value


def code_text(value):
    return str(value).strip() if value is not None else ""


def tidy_typed_name(name, default_name="LOCAL SALES", generic=("", "CASH", "LOCAL", "LOCAL SALES", "CASH SALES")):
    """Clean up a customer name typed on a cash bill. None = walk-in.

    Staff often type over the default name, leaving the end of it behind
    ("JOHNcal Sales", "MARYales"), and add "-gpay" or a phone number.
    """
    name = re.sub(r"\s+", " ", (name or "").upper()).strip()
    for size in range(len(default_name), 3, -1):
        if name.endswith(default_name[-size:]):
            name = name[:-size]
            break
    name = re.sub(r"[\s-]*(G-?PAY|\d{10})$", "", name).strip(" -")
    return None if name in set(generic) else name


def apply_bill_adjustment(net, lines):
    """Scale a bill's lines so they add up to the bill's NetAmount.

    The difference is a discount or round-off on the whole bill. It's
    spread over the lines in proportion to their value. A bill whose total
    is far from its lines (under half or over 1.5 times) is left alone:
    that's a data problem, not a discount.
    """
    total = sum(line["sales_value"] for line in lines)
    if not total or not net:
        return
    factor = net / total
    if abs(factor - 1) < 1e-9 or not 0.5 <= factor <= 1.5:
        return
    for line in lines:
        line["sales_value"] *= factor
        line["sales_ex_tax"] *= factor


class LuxSource(Source):
    label = "LUX"

    def __init__(self, config, settings=None):
        super().__init__(config, settings)
        self.database = os.environ.get("LUX_DATABASE") or config.get("database")
        self.sqlite = os.environ.get("LUX_SQLITE") or config.get("sqlite")
        self.debtors_group = config.get("debtors_group", 20)
        self.creditors_group = config.get("creditors_group", 21)
        self.cash_account = config.get("cash_account", "CASH SALES").upper()
        self.default_typed_name = config.get("default_typed_name", "LOCAL SALES").upper()
        # Quotations price from LUX's stock report export (P/Rate+Tax) until
        # live rates are checked against it; see quote_catalogue in the config.
        self.catalogue_csv = config.get("catalogue_csv")

    # ------------------------------------------------------------------

    def connect(self):
        if self.sqlite:
            from .sqlite_copy import connect
            return connect(self.sqlite)
        if not self.database:
            raise ValueError("Set [source] database (the LUX .mdb file) or sqlite in the customer config.")
        import pyodbc
        return pyodbc.connect(
            r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + self.database + ";READONLY=1;",
            readonly=True,
        )

    def checked_at(self):
        """When the data was saved: the .mdb's modified time (set `database`
        alongside `sqlite` to a downloaded snapshot so this stays its time),
        else the SQLite copy's."""
        for path in (self.database, self.sqlite):
            if path and os.path.exists(path):
                return datetime.fromtimestamp(os.path.getmtime(path)).astimezone()
        return datetime.now().astimezone()

    def load(self):
        connection = self.connect()
        try:
            cursor = connection.cursor()
            accounts = self._accounts(cursor)
            purchase_costs = self._purchase_costs(cursor)
            item_rates = self._item_rates(cursor)
            items = self._items(cursor, purchase_costs, item_rates)
            lines, bills = self._sales(cursor, accounts, purchase_costs, item_rates)
            purchases, purchase_lines = self._purchases(cursor, accounts)
            ledger = self._ledger(cursor)
        finally:
            connection.close()

        def balances(group, sign):
            return [
                {"party_id": code, "name": account["name"], "balance": sign * (account["opening"] + ledger.get(code, 0.0))}
                for code, account in accounts.items() if account["group"] == group
            ]

        return {
            "items": items,
            "sales_lines": lines,
            "bills": bills,
            "purchases": purchases,
            "purchase_lines": purchase_lines,
            "receivables": balances(self.debtors_group, 1),
            "payables": balances(self.creditors_group, -1),
            "checked_at": self.checked_at(),
        }

    def load_catalogue(self, data=None):
        if self.catalogue_csv:
            from ...quote.csv_catalogue import load_stock_report_csv
            return load_stock_report_csv(self.catalogue_csv)
        return super().load_catalogue(data)

    # ------------------------------------------------------------------

    def _accounts(self, cursor):
        cursor.execute("SELECT code, AcName, GrpId, op_bal, Op_Crdr FROM Account")
        accounts = {}
        for row in cursor.fetchall():
            opening = float(row.op_bal or 0)
            if code_text(row.Op_Crdr).upper() == "CR":
                opening = -opening
            accounts[code_text(row.code)] = {
                "name": (row.AcName or "").strip(),
                "group": row.GrpId,
                "opening": opening,
            }
        return accounts

    def _ledger(self, cursor):
        cursor.execute("SELECT Code, Byto, SUM(Amount) FROM AccTransChld GROUP BY Code, Byto")
        ledger = defaultdict(float)
        for code, side, amount in cursor.fetchall():
            sign = 1 if code_text(side).upper() == "DR" else -1
            ledger[code_text(code)] += sign * float(amount or 0)
        return dict(ledger)

    def _purchase_costs(self, cursor):
        """Average purchase-bill rate before GST (after discount) per item."""
        cursor.execute(f"""
            SELECT C.ItemCode, SUM(C.TaxableAmt), SUM(C.Totalqty)
            FROM PurchaseChild AS C
            INNER JOIN purchasemaster AS M
            ON C.InvoiceNo = M.InvoiceNo
            AND Trim(C.FormNo) = Trim(M.FormNo)
            WHERE M.{NOT_CANCELLED}
            GROUP BY C.ItemCode
        """)
        return {code: float(taxable) / float(qty) for code, taxable, qty in cursor.fetchall() if qty and taxable}

    def _item_rates(self, cursor):
        cursor.execute("SELECT ItemCode, PurchRate FROM ItemMaster")
        return {row.ItemCode: float(row.PurchRate) for row in cursor.fetchall() if row.PurchRate and row.PurchRate > 0}

    def _cost(self, code, purchase_costs, item_rates):
        if code in purchase_costs:
            return purchase_costs[code], "bill"
        if code in item_rates:
            return item_rates[code], "item"
        return None, "none"

    def _items(self, cursor, purchase_costs, item_rates):
        cursor.execute("SELECT ItemCode, itemname, OpeningStock FROM ItemMaster")
        items = {
            row.ItemCode: {"code": row.ItemCode, "name": row.itemname, "stock": float(row.OpeningStock or 0)}
            for row in cursor.fetchall()
        }
        for child, master, sign in STOCK_MOVEMENTS:
            cursor.execute(f"""
                SELECT C.ItemCode, SUM(C.Totalqty)
                FROM {child} AS C
                INNER JOIN {master} AS M
                ON C.InvoiceNo = M.InvoiceNo
                AND Trim(C.FormNo) = Trim(M.FormNo)
                WHERE M.{NOT_CANCELLED}
                GROUP BY C.ItemCode
            """)
            # Lines for item codes no longer in ItemMaster are left out, as in LUX.
            for code, qty in cursor.fetchall():
                if code in items:
                    items[code]["stock"] += sign * float(qty or 0)
        for item in items.values():
            item["stock"] = round(item["stock"], 3)
            item["unit_cost"], item["cost_source"] = self._cost(item["code"], purchase_costs, item_rates)
        return list(items.values())

    def _customer(self, party, typed_name, accounts):
        account = accounts.get(party)
        if account and account["group"] == self.debtors_group and account["name"].upper() != self.cash_account:
            return account["name"]
        return tidy_typed_name(typed_name, self.default_typed_name)

    def _sales(self, cursor, accounts, purchase_costs, item_rates):
        lines, bills = [], []
        for child, master, sign in SALES_TABLES:
            is_return = sign < 0
            prefix = "R:" if is_return else ""

            cursor.execute(f"""
                SELECT TransDate, InvoiceNo, FormNo, PartyCode, SalesType, cname, NetAmount
                FROM {master}
                WHERE {NOT_CANCELLED}
            """)
            masters = {}
            for row in cursor.fetchall():
                party = code_text(row.PartyCode)
                bill_id = f"{prefix}{code_text(row.FormNo)}/{row.InvoiceNo}"
                bill = {
                    "date": as_date(row.TransDate),
                    "bill_id": bill_id,
                    "party_id": party,
                    "customer": self._customer(party, row.cname, accounts),
                    "credit": code_text(row.SalesType).upper() == "CR",
                    "net": sign * float(row.NetAmount or 0),
                    "is_return": is_return,
                }
                bills.append(bill)
                masters[bill_id] = (bill, str(row.InvoiceNo))

            cursor.execute(f"""
                SELECT M.InvoiceNo, M.FormNo, C.ItemCode, I.itemname,
                       C.Totalqty, C.TaxableAmt, C.TaxAmt, C.IGSTAmount
                FROM
                    ({child} AS C
                    INNER JOIN {master} AS M
                    ON C.InvoiceNo = M.InvoiceNo
                    AND Trim(C.FormNo) = Trim(M.FormNo))
                    INNER JOIN ItemMaster AS I
                    ON C.ItemCode = I.ItemCode
                WHERE M.{NOT_CANCELLED}
            """)
            by_bill = defaultdict(list)
            for row in cursor.fetchall():
                bill_id = f"{prefix}{code_text(row.FormNo)}/{row.InvoiceNo}"
                bill, bill_no = masters[bill_id]
                unit_cost, cost_source = self._cost(row.ItemCode, purchase_costs, item_rates)
                taxable = float(row.TaxableAmt or 0)
                line = {
                    "date": bill["date"],
                    "bill_id": bill_id,
                    "bill_no": bill_no,
                    "party_id": bill["party_id"],
                    "customer": bill["customer"],
                    "credit": bill["credit"],
                    "item_code": row.ItemCode,
                    "product": row.itemname,
                    "qty": sign * float(row.Totalqty or 0),
                    "sales_ex_tax": sign * taxable,
                    "sales_value": sign * (taxable + 2 * float(row.TaxAmt or 0) + float(row.IGSTAmount or 0)),
                    "unit_cost": unit_cost,
                    "cost_source": cost_source,
                    "is_return": is_return,
                }
                lines.append(line)
                by_bill[bill_id].append(line)

            for bill_id, bill_lines in by_bill.items():
                apply_bill_adjustment(masters[bill_id][0]["net"], bill_lines)

        return lines, bills

    def _purchases(self, cursor, accounts):
        def supplier(party):
            return accounts.get(party, {}).get("name") or "Unknown supplier"

        purchases = []
        for table, sign in (("purchasemaster", 1), ("PurchaseReturnMaster", -1)):
            cursor.execute(f"SELECT TransDate, PartyCode, NetAmount FROM {table} WHERE {NOT_CANCELLED}")
            for row in cursor.fetchall():
                party = code_text(row.PartyCode)
                purchases.append({
                    "date": as_date(row.TransDate),
                    "party_id": party,
                    "supplier": supplier(party),
                    "net": sign * float(row.NetAmount or 0),
                    "is_return": sign < 0,
                })

        cursor.execute(f"""
            SELECT M.TransDate, C.ItemCode, M.PartyCode, C.TaxableAmt, C.Totalqty
            FROM PurchaseChild AS C
            INNER JOIN purchasemaster AS M
            ON C.InvoiceNo = M.InvoiceNo
            AND Trim(C.FormNo) = Trim(M.FormNo)
            WHERE M.{NOT_CANCELLED}
        """)
        purchase_lines = [
            {
                "date": as_date(row.TransDate),
                "item_code": row.ItemCode,
                "supplier": supplier(code_text(row.PartyCode)),
                "taxable": float(row.TaxableAmt or 0),
                "qty": float(row.Totalqty or 0),
            }
            for row in cursor.fetchall()
        ]
        return purchases, purchase_lines

