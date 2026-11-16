"""Write made-up demo data to demo_data/ (the DemoSource CSV layout).

A small hardware shop over 60 days, with the awkward cases every source
has to handle: a sales return, discounts on the whole bill, credit
customers who owe money, an item sold below cost, an item with no cost,
negative stock, stock that hasn't moved, and items running low.

    python tools/make_demo_data.py

Fixed random seed and dates, so the tests can rely on the figures.
"""

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from pulse_bi.model import REQUIRED  # noqa: E402

OUT = REPO / "demo_data"
END = date(2026, 10, 31)
DAYS = 60
GST = 0.18

# code, name, cost before tax (None = no cost), selling price before tax, opening stock, sales per day
ITEMS = [
    ("A100", "Aluminium angle 1 x 1 in, 12 ft", 410.0, 520.0, 60, 2.0),
    ("A101", "Aluminium angle 1 1/2 x 1 in, 12 ft", 520.0, 650.0, 40, 1.4),
    ("A102", "Aluminium square tube 1 in, 12 ft", 610.0, 760.0, 30, 1.0),
    ("A103", "Aluminium channel 3/4 in, 12 ft", 380.0, 470.0, 25, 0.5),
    ("D200", "PVC door 30 x 78 in, white", 2650.0, 3300.0, 12, 0.35),
    ("D201", "PVC door 32 x 80 in, grey", 2900.0, 3600.0, 8, 0.25),
    ("D202", "Flush door 30 x 78 in", 3400.0, 3350.0, 6, 0.1),       # priced below cost
    ("H300", "Steel hinge 4 in (pair)", 38.0, 55.0, 300, 9.0),
    ("H301", "Tower bolt 6 in", 42.0, 60.0, 150, 3.0),
    ("H302", "Door handle, steel", 120.0, 175.0, 80, 1.5),
    ("H303", "Mortise lock set", 650.0, 820.0, 15, 0.4),
    ("H304", "Pop rivets 4 mm (box of 100)", 95.0, 130.0, 40, 1.2),
    ("H305", "Self-drilling screws 1 in (box)", 160.0, 215.0, 3, 0.9),  # running low
    ("S400", "PVC sheet 8 x 4 ft, 5 mm", 1450.0, 1800.0, 20, 0.6),
    ("S401", "ACP sheet 8 x 4 ft, 3 mm", 2100.0, 2600.0, 10, 0.2),
    ("S402", "Polycarbonate sheet 8 x 4 ft", 1900.0, 2450.0, 9, 0.0),    # not moving
    ("W500", "Wall panel 8 x 4 ft, oak", 980.0, 1250.0, 18, 0.5),
    ("W501", "Wall panel 8 x 4 ft, marble look", 1150.0, 1450.0, 2, 0.4),  # sells into negative stock
    ("M600", "Mosquito net roll 4 ft", 1300.0, 1650.0, 7, 0.3),
    ("M601", "Mosquito net frame kit", None, 900.0, 10, 0.2),          # no cost in the system
    ("K700", "Kitchen drawer channel 18 in", 210.0, 290.0, 50, 1.0),
    ("K701", "Cabinet handle 6 in", 65.0, 95.0, 120, 2.5),
    ("L800", "Aluminium ladder 6 ft", 2400.0, 3100.0, 4, 0.07),
    ("L801", "Aluminium ladder 8 ft", 3200.0, 4100.0, 3, 0.0),           # not moving
]

CREDIT_CUSTOMERS = [("C01", "Sunrise Interiors"), ("C02", "Metro Fabricators"), ("C03", "Green Homes Builders")]
CASH_NAMES = ["Ravi", "Anil", "Joseph", "Fatima", "Suresh", "Meena", None, None, None, None]
SUPPLIERS = [("S01", "Coastal Aluminium Traders"), ("S02", "Prime Hardware Distributors"), ("S03", "Unity Panels")]


def write(name, rows):
    fields = list(REQUIRED[name].__annotations__)
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row[k] is None else row[k].isoformat() if isinstance(row[k], date) else row[k])
                             for k in fields})


def main():
    random.seed(7)
    OUT.mkdir(exist_ok=True)
    start = END - timedelta(days=DAYS - 1)
    stock = {code: float(opening) for code, _, _, _, opening, _ in ITEMS}
    info = {code: (name, cost, price) for code, name, cost, price, _, _ in ITEMS}

    lines, bills, purchases, purchase_lines = [], [], [], []
    bought = {code: [] for code in info}
    bill_no = 1000
    owed = {code: 0.0 for code, _ in CREDIT_CUSTOMERS}
    to_pay = {code: 0.0 for code, _ in SUPPLIERS}

    for offset in range(DAYS):
        day = start + timedelta(days=offset)
        if day.weekday() == 6:      # closed on Sundays
            continue

        # Purchases on Mondays top up items that are low.
        if day.weekday() == 0:
            for number, (supplier_code, supplier) in enumerate(SUPPLIERS):
                net = 0.0
                for index, (code, name, cost, _, opening, pace) in enumerate(ITEMS):
                    if cost is None or pace == 0 or index % len(SUPPLIERS) != number:
                        continue
                    if stock[code] < pace * 14 and code not in ("H305", "W501"):
                        qty = max(2, round(pace * 25))
                        taxable = round(cost * random.uniform(0.97, 1.03) * qty, 2)
                        purchase_lines.append({"date": day, "item_code": code, "supplier": supplier,
                                               "taxable": taxable, "qty": qty})
                        bought[code].append((taxable, qty))
                        stock[code] += qty
                        net += taxable * (1 + GST)
                if net:
                    purchases.append({"date": day, "party_id": supplier_code, "supplier": supplier,
                                      "net": round(net, 2), "is_return": False})
                    to_pay[supplier_code] += net

        # Sales.
        busy = 1.25 if day.weekday() == 5 else 1.0
        for _ in range(random.randint(4, 9)):
            bill_no += 1
            credit_customer = random.random() < 0.2
            party, customer = random.choice(CREDIT_CUSTOMERS) if credit_customer else ("", random.choice(CASH_NAMES))
            bill_lines = []
            for code, name, cost, price, _, pace in ITEMS:
                if pace and random.random() < pace * busy / 6:
                    qty = max(1, round(random.expovariate(1.2)))
                    unit = round(price * random.uniform(0.95, 1.02), 2)
                    if code == "H300" and bill_no == 1050:
                        unit = round(price / 10, 2)   # a mistyped rate
                    bill_lines.append((code, qty, unit))
            if not bill_lines:
                continue
            bill_id = f"S/{bill_no}"
            raw = sum(qty * unit * (1 + GST) for _, qty, unit in bill_lines)
            net = raw
            if raw > 2000 and random.random() < 0.3:
                net = float(int(raw // 50) * 50)     # rounded down: a discount on the whole bill
            factor = net / raw
            for code, qty, unit in bill_lines:
                name, cost, _ = info[code]
                ex_tax = round(qty * unit * factor, 4)
                lines.append({
                    "date": day, "bill_id": bill_id, "bill_no": str(bill_no), "party_id": party,
                    "customer": customer, "credit": credit_customer, "item_code": code, "product": name,
                    "qty": qty, "sales_ex_tax": ex_tax, "sales_value": round(ex_tax * (1 + GST), 4),
                    "unit_cost": None, "cost_source": "none", "is_return": False,
                })
                stock[code] -= qty
            bills.append({"date": day, "bill_id": bill_id, "party_id": party, "customer": customer,
                          "credit": credit_customer, "net": round(net, 2), "is_return": False})
            if credit_customer:
                owed[party] += net

    # A sales return: two doors brought back ten days before the end.
    day = END - timedelta(days=10)
    name, cost, price = info["D200"]
    lines.append({"date": day, "bill_id": "R/1", "bill_no": "R1", "party_id": "C01", "customer": "Sunrise Interiors",
                  "credit": True, "item_code": "D200", "product": name, "qty": -2, "sales_ex_tax": -2 * price,
                  "sales_value": -2 * price * (1 + GST), "unit_cost": None, "cost_source": "none", "is_return": True})
    bills.append({"date": day, "bill_id": "R/1", "party_id": "C01", "customer": "Sunrise Interiors",
                  "credit": True, "net": round(-2 * price * (1 + GST), 2), "is_return": True})
    stock["D200"] += 2
    owed["C01"] -= 2 * price * (1 + GST)

    # Unit cost: average purchase price, else the opening cost; none for M601.
    for line in lines:
        name, cost, _ = info[line["item_code"]]
        if cost is None:
            continue
        history = bought[line["item_code"]]
        line["unit_cost"] = round(sum(t for t, _ in history) / sum(q for _, q in history), 4) if history else cost
        line["cost_source"] = "bill" if history else "item"

    items = []
    for code, name, cost, _, _, _ in ITEMS:
        history = bought[code]
        unit_cost = round(sum(t for t, _ in history) / sum(q for _, q in history), 4) if history else cost
        items.append({"code": code, "name": name, "stock": round(stock[code], 3), "unit_cost": unit_cost,
                      "cost_source": "none" if cost is None else ("bill" if history else "item")})

    # Customers paid most of their old bills; the shop paid most suppliers.
    receivables = [{"party_id": code, "name": name, "balance": round(owed[code] * share, 2)}
                   for (code, name), share in zip(CREDIT_CUSTOMERS, (0.35, 0.6, 0.15))]
    payables = [{"party_id": code, "name": name, "balance": round(to_pay[code] * share, 2)}
                for (code, name), share in zip(SUPPLIERS, (0.4, 0.25, 0.0))]

    write("items", items)
    write("sales_lines", lines)
    write("bills", bills)
    write("purchases", purchases)
    write("purchase_lines", purchase_lines)
    write("receivables", receivables)
    write("payables", payables)
    print(f"Wrote {len(bills)} bills, {len(lines)} lines, {len(purchases)} purchases to {OUT}")


if __name__ == "__main__":
    main()
