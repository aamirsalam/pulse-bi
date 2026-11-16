"""Business insights from a BusinessData dict (see pulse_bi.model).

Pure Python: no database access, so it works the same for every source and
can be tested with made-up data. Thresholds come from the customer's
config ([insights] in customers/<name>.toml), with the defaults below.
"""

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

WALK_IN = "Walk-in (no name)"
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
AGEING_BUCKETS = ((0, 30, "0 to 30 days"), (31, 60, "31 to 60 days"), (61, None, "Over 60 days"))


@dataclass
class Settings:
    reorder_lookback_days: int = 30   # sales pace is measured over the last 30 days
    reorder_cover_days: int = 14      # flag items with less than two weeks of stock left
    reorder_target_days: int = 30     # suggested order tops stock up to a month of sales
    reorder_min_sale_days: int = 2    # ignore one-off orders (sold on a single day)
    dead_stock_days: int = 30         # stock with no sale in this many days is "not moving"
    low_margin_percent: float = 10
    # Margin checks ignore bills before this date, e.g. the first days on a
    # new system before prices were set up. Totals still include them.
    margin_ignore_before: Optional[date] = None

    @classmethod
    def from_config(cls, section):
        section = dict(section or {})
        ignore = section.get("margin_ignore_before")
        if isinstance(ignore, str):
            section["margin_ignore_before"] = date.fromisoformat(ignore)
        known = cls.__dataclass_fields__
        return cls(**{key: value for key, value in section.items() if key in known})


def customer_label(row):
    return row.get("customer") or WALK_IN


def latest_date(data):
    return max((line["date"] for line in data["sales_lines"]), default=None)


# --------------------------------------------------------------------------
# Periods


def period_range(period, today):
    """(start, end, previous_start, previous_end) for a dashboard period.

    The previous range is the same number of days just before; for "month"
    it's the same days of last month (1-4 Nov vs 1-4 Oct). "all" has no
    start and no previous range.
    """
    if period == "7d":
        start = today - timedelta(days=6)
    elif period == "30d":
        start = today - timedelta(days=29)
    elif period == "month":
        start = today.replace(day=1)
        previous_start = (start - timedelta(days=1)).replace(day=1)
        previous_end = min(previous_start + (today - start), start - timedelta(days=1))
        return start, today, previous_start, previous_end
    else:
        return None, today, None, None

    length = today - start
    previous_end = start - timedelta(days=1)
    return start, today, previous_end - length, previous_end


def in_range(day, start, end):
    return (start is None or day >= start) and day <= end


PERIOD_LABELS = {
    "7d": ("Last 7 days", "previous 7 days"),
    "30d": ("Last 30 days", "previous 30 days"),
    "month": ("This month", "same days last month"),
    "all": ("All time", None),
}
PERIODS = tuple(PERIOD_LABELS)


# --------------------------------------------------------------------------
# Sales


def line_profit(line):
    if line["unit_cost"] is None:
        return None
    return line["sales_ex_tax"] - line["unit_cost"] * line["qty"]


def summarise_profit(lines):
    costed = [line for line in lines if line["unit_cost"] is not None]
    missing = [line for line in lines if line["unit_cost"] is None]
    profit = sum(line_profit(line) for line in costed)
    sales_ex_tax = sum(line["sales_ex_tax"] for line in costed)
    return {
        "profit_total": profit,
        "profit_sales_ex_tax": sales_ex_tax,
        "profit_margin": profit / sales_ex_tax * 100 if sales_ex_tax else 0,
        "profit_fallback_lines": sum(1 for line in costed if line["cost_source"] == "item"),
        "profit_missing_lines": len(missing),
        "profit_missing_sales": sum(line["sales_ex_tax"] for line in missing),
    }


def daily_sales(bills, lines):
    """Bills, sales and profit per day, newest first. Returns are taken off
    on the day of the return but don't count as bills."""
    days = {}
    for bill in bills:
        day = days.setdefault(bill["date"], {"date": bill["date"], "invoice_count": 0,
                                             "net_sales": 0.0, "profit": 0.0, "sales_ex_tax": 0.0})
        day["net_sales"] += bill["net"]
        if not bill["is_return"]:
            day["invoice_count"] += 1
    for line in lines:
        profit = line_profit(line)
        if profit is None or line["date"] not in days:
            continue
        days[line["date"]]["profit"] += profit
        days[line["date"]]["sales_ex_tax"] += line["sales_ex_tax"]
    return sorted(days.values(), key=lambda day: day["date"], reverse=True)


def sales_summary(bills):
    billed = [bill for bill in bills if not bill["is_return"]]
    return {
        "sales_invoice_count": len(billed),
        "sales_first_date": min((bill["date"] for bill in billed), default=None),
        "sales_last_date": max((bill["date"] for bill in billed), default=None),
        "sales_net_amount": sum(bill["net"] for bill in bills),
    }


def top_products(lines, period, today, limit=10):
    """Best sellers by sales value in the period."""
    start, end, _, _ = period_range(period, today)
    products = {}
    for line in lines:
        if not in_range(line["date"], start, end):
            continue
        product = products.setdefault(line["item_code"], {
            "product": line["product"], "qty_sold": 0.0, "sales_value": 0.0,
            "profit": 0.0, "cost_incomplete": False,
        })
        product["qty_sold"] += line["qty"]
        product["sales_value"] += line["sales_value"]
        profit = line_profit(line)
        if profit is None:
            product["cost_incomplete"] = True
        else:
            product["profit"] += profit
    return sorted(products.values(), key=lambda p: p["sales_value"], reverse=True)[:limit]


def sales_figures(bills, lines, start, end):
    chosen = [bill for bill in bills if in_range(bill["date"], start, end)]
    net = sum(bill["net"] for bill in chosen)  # net of returns
    credit = sum(bill["net"] for bill in chosen if bill["credit"])
    counted = [bill for bill in chosen if not bill["is_return"]]

    profit = sales_ex_tax = 0.0
    for line in lines:
        if in_range(line["date"], start, end):
            value = line_profit(line)
            if value is not None:
                profit += value
                sales_ex_tax += line["sales_ex_tax"]

    return {
        "net_sales": net,
        "invoices": len(counted),
        "avg_invoice": net / len(counted) if counted else 0.0,
        "profit": profit,
        "margin": profit / sales_ex_tax * 100 if sales_ex_tax else 0.0,
        "credit_share": credit / net * 100 if net else 0.0,
        "selling_days": len({bill["date"] for bill in counted}),
    }


def percent_change(current, previous):
    if not previous:
        return None
    return (current - previous) / abs(previous) * 100


def period_comparison(bills, lines, period, today):
    start, end, previous_start, previous_end = period_range(period, today)
    current = sales_figures(bills, lines, start, end)
    label, previous_label = PERIOD_LABELS[period]
    first_sale = min((bill["date"] for bill in bills), default=None)

    comparison = {
        "label": label,
        "previous_label": previous_label,
        "start": start or first_sale,
        "end": end,
        "current": current,
        "previous": None,
        "change": {},
    }

    if previous_start is not None and first_sale and previous_end < first_sale:
        comparison["no_previous"] = True  # nothing recorded before this period
    elif previous_start is not None:
        previous = sales_figures(bills, lines, previous_start, previous_end)
        comparison.update(previous=previous, previous_start=previous_start,
                          previous_end=previous_end, records_start=first_sale)
        # Records start partway through the previous range, so a % change
        # would compare a full period against a few days.
        comparison["previous_partial"] = bool(first_sale and previous_start < first_sale)
        if comparison["previous_partial"]:
            return comparison
        comparison["change"] = {
            "net_sales": percent_change(current["net_sales"], previous["net_sales"]),
            "invoices": percent_change(current["invoices"], previous["invoices"]),
            "avg_invoice": percent_change(current["avg_invoice"], previous["avg_invoice"]),
            "profit": percent_change(current["profit"], previous["profit"]),
            # Margin changes in percentage points, not %.
            "margin": current["margin"] - previous["margin"] if previous["invoices"] else None,
        }
    return comparison


def weekday_pattern(bills):
    """Average sales on each weekday over the whole history."""
    if not bills:
        return []
    first = min(bill["date"] for bill in bills)
    last = max(bill["date"] for bill in bills)

    totals = [0.0] * 7
    for bill in bills:
        totals[bill["date"].weekday()] += bill["net"]
    occurrences = [0] * 7
    day = first
    while day <= last:
        occurrences[day.weekday()] += 1
        day += timedelta(days=1)

    averages = [totals[i] / occurrences[i] if occurrences[i] else 0.0 for i in range(7)]
    top = max(averages) or 1
    return [
        {"day": WEEKDAYS[i], "average": averages[i], "share": averages[i] / top * 100,
         "best": averages[i] == top and averages[i] > 0}
        for i in range(7)
    ]


# --------------------------------------------------------------------------
# Stock


def unit_costs(items):
    return {item["code"]: item["unit_cost"] for item in items if item["unit_cost"] is not None}


def last_purchases(purchase_lines):
    latest = {}
    for line in purchase_lines:
        current = latest.get(line["item_code"])
        if current is None or line["date"] >= current["date"]:
            latest[line["item_code"]] = line
    return {
        code: {
            "date": line["date"],
            "supplier": line["supplier"] or "Unknown supplier",
            "rate": line["taxable"] / line["qty"] if line["qty"] else None,
        }
        for code, line in latest.items()
    }


def reorder_alerts(items, lines, last_bought, today, settings):
    """Items selling fast enough to run out within reorder_cover_days."""
    lookback_start = today - timedelta(days=settings.reorder_lookback_days - 1)
    first_sale = min((line["date"] for line in lines), default=today)
    # Early on there may be fewer days of sales than the lookback.
    window = max(1, min(settings.reorder_lookback_days, (today - first_sale).days + 1))

    sold = defaultdict(float)
    sale_days = defaultdict(set)
    for line in lines:
        if lookback_start <= line["date"] <= today:
            sold[line["item_code"]] += line["qty"]
            sale_days[line["item_code"]].add(line["date"])

    alerts = []
    for item in items:
        code = item["code"]
        if sold[code] <= 0 or len(sale_days[code]) < settings.reorder_min_sale_days:
            continue
        per_day = sold[code] / window
        stock = item["stock"]
        days_left = max(stock, 0) / per_day
        if days_left >= settings.reorder_cover_days:
            continue
        alerts.append({
            "code": code,
            "name": item["name"],
            "stock": stock,
            "sold": sold[code],
            "sale_days": len(sale_days[code]),
            "per_day": per_day,
            "days_left": days_left,
            "suggested": math.ceil(per_day * settings.reorder_target_days - max(stock, 0)),
            "last_bought": last_bought.get(code),
        })
    alerts.sort(key=lambda alert: (alert["days_left"], -alert["per_day"]))
    return {"items": alerts, "window_days": window}


def stock_health(items, lines, last_bought, today, settings):
    """Stock value at cost, how long it lasts, and stock that isn't moving.

    Not moving = in stock, no sale in dead_stock_days and not bought in that
    time either (new arrivals haven't had a chance to sell yet).
    """
    last_sold = {}
    for line in lines:
        if line["date"] > last_sold.get(line["item_code"], date.min):
            last_sold[line["item_code"]] = line["date"]

    dead_cutoff = today - timedelta(days=settings.dead_stock_days)
    first_sale = min((line["date"] for line in lines), default=None)

    total_value = 0.0
    uncosted = 0
    dead = []
    new_arrivals = 0
    for item in items:
        if item["stock"] <= 0:
            continue
        cost = item["unit_cost"]
        if cost is None:
            uncosted += 1
            value = None
        else:
            value = item["stock"] * cost
            total_value += value

        sold_on = last_sold.get(item["code"])
        if sold_on is not None and sold_on >= dead_cutoff:
            continue
        bought = last_bought.get(item["code"])
        if bought and bought["date"] >= dead_cutoff:
            new_arrivals += 1
            continue
        dead.append({
            "code": item["code"], "name": item["name"], "stock": item["stock"], "value": value,
            "last_sold": sold_on, "last_bought": bought["date"] if bought else None,
        })

    dead.sort(key=lambda item: item["value"] or 0, reverse=True)
    dead_value = sum(item["value"] or 0 for item in dead)

    # Cost of goods sold per day over the lookback, to say how many days of
    # sales the stock on hand would cover.
    window_start = today - timedelta(days=settings.reorder_lookback_days - 1)
    window = settings.reorder_lookback_days
    if first_sale and first_sale > window_start:
        window = (today - first_sale).days + 1
    cost_sold = sum(
        line["unit_cost"] * line["qty"] for line in lines
        if line["unit_cost"] is not None and window_start <= line["date"] <= today
    )
    cost_per_day = cost_sold / window if window > 0 else 0

    return {
        "value": total_value,
        "uncosted_items": uncosted,
        "cover_days": total_value / cost_per_day if cost_per_day else None,
        "dead_items": dead,
        "dead_count": len(dead),
        "dead_value": dead_value,
        "dead_share": dead_value / total_value * 100 if total_value else 0.0,
        "never_sold": sum(1 for item in dead if item["last_sold"] is None),
        "new_arrivals": new_arrivals,
        "first_sale": first_sale,
    }


# --------------------------------------------------------------------------
# Margins


def margin_watch(lines, period, today, settings):
    start, end, _, _ = period_range(period, today)
    ignore_before = settings.margin_ignore_before
    items = {}
    for line in lines:
        if not in_range(line["date"], start, end) or line["unit_cost"] is None:
            continue
        if ignore_before and line["date"] < ignore_before:
            continue
        item = items.setdefault(line["item_code"], {
            "code": line["item_code"], "name": line["product"], "qty": 0.0, "sales": 0.0, "cost": 0.0,
        })
        item["qty"] += line["qty"]
        item["sales"] += line["sales_ex_tax"]
        item["cost"] += line["unit_cost"] * line["qty"]

    loss, low = [], []
    for item in items.values():
        item["profit"] = item["sales"] - item["cost"]
        item["margin"] = item["profit"] / item["sales"] * 100 if item["sales"] else None
        item["avg_price"] = item["sales"] / item["qty"] if item["qty"] else None
        item["unit_cost"] = item["cost"] / item["qty"] if item["qty"] else None
        if item["profit"] < 0:
            loss.append(item)
        elif item["margin"] is not None and item["margin"] < settings.low_margin_percent:
            low.append(item)

    loss.sort(key=lambda item: item["profit"])
    low.sort(key=lambda item: item["margin"])
    return {
        "loss_items": loss,
        "loss_total": -sum(item["profit"] for item in loss),
        "low_items": low,
        "low_margin_percent": settings.low_margin_percent,
        "ignored_before": ignore_before if ignore_before and (start is None or start < ignore_before) else None,
    }


# --------------------------------------------------------------------------
# Customers and suppliers


def customer_insights(bills, period, today, limit=10):
    start, end, _, _ = period_range(period, today)
    customers = {}
    for bill in bills:
        if not in_range(bill["date"], start, end):
            continue
        name = customer_label(bill)
        customer = customers.setdefault(name, {
            "name": name, "sales": 0.0, "invoices": 0, "days": set(),
            "last": bill["date"], "credit": False,
        })
        customer["sales"] += bill["net"]  # a return takes its amount off
        if bill["is_return"]:
            continue
        customer["invoices"] += 1
        customer["days"].add(bill["date"])
        customer["last"] = max(customer["last"], bill["date"])
        customer["credit"] = customer["credit"] or bill["credit"]

    # A customer with only a return in the period isn't counted as a buyer.
    named = [c for c in customers.values() if c["name"] != WALK_IN and c["invoices"]]
    walk_in = customers.get(WALK_IN)
    repeat = [c for c in named if len(c["days"]) >= 2]

    total = sum(c["sales"] for c in customers.values())
    named_total = sum(c["sales"] for c in named)
    repeat_total = sum(c["sales"] for c in repeat)

    ranked = sorted(named, key=lambda c: c["sales"], reverse=True)
    for customer in ranked:
        customer["visits"] = len(customer.pop("days"))
        customer["share"] = customer["sales"] / total * 100 if total else 0

    top = ranked[:limit]
    return {
        "top": top,
        "top_share": sum(c["sales"] for c in top) / total * 100 if total else 0,
        "named_count": len(named),
        "repeat_count": len(repeat),
        "repeat_share": repeat_total / named_total * 100 if named_total else 0,
        "walk_in_sales": walk_in["sales"] if walk_in else 0.0,
        "walk_in_invoices": walk_in["invoices"] if walk_in else 0,
        "total": total,
    }


def age_balance(balance, bills, today):
    """Split a balance over the newest bills (first in, first out).

    Payments are assumed to clear the oldest bills first, so what's still
    owed is made up of the most recent bills. Anything left over after all
    the recorded bills is an opening balance brought forward.
    """
    buckets = [0.0] * len(AGEING_BUCKETS)
    remaining = balance
    oldest = None
    for bill in sorted(bills, key=lambda bill: bill["date"], reverse=True):
        if remaining <= 0.005:
            break
        part = min(bill["net"], remaining)
        remaining -= part
        oldest = bill["date"]
        age = (today - bill["date"]).days
        for index, (low, high, _) in enumerate(AGEING_BUCKETS):
            if age >= low and (high is None or age <= high):
                buckets[index] += part
                break

    opening_part = max(remaining, 0.0)
    if opening_part > 0.005:
        buckets[-1] += opening_part
    return {
        "buckets": buckets,
        "oldest": oldest,
        "days": (today - oldest).days if oldest else None,
        "from_opening": opening_part > 0.005,
    }


def outstanding(balances, bills_by_party, today):
    """Money owed to the shop (receivables) or by it (payables), aged."""
    parties = []
    for row in balances:
        amount = row["balance"]
        if amount < 1:  # settled, overpaid or rounding
            continue
        parties.append({
            "code": row["party_id"], "name": row["name"], "amount": amount,
            **age_balance(amount, bills_by_party.get(row["party_id"], []), today),
        })
    parties.sort(key=lambda party: party["amount"], reverse=True)
    totals = [sum(p["buckets"][i] for p in parties) for i in range(len(AGEING_BUCKETS))]
    return {
        "parties": parties,
        "total": sum(p["amount"] for p in parties),
        "buckets": [{"label": label, "amount": totals[i]} for i, (_, _, label) in enumerate(AGEING_BUCKETS)],
    }


def supplier_spend(purchases, period, today, limit=8):
    start, end, _, _ = period_range(period, today)
    spend = defaultdict(lambda: {"name": "", "amount": 0.0, "bills": 0})
    for bill in purchases:
        if in_range(bill["date"], start, end):
            entry = spend[bill["party_id"]]
            entry["name"] = entry["name"] or bill["supplier"] or "Unknown supplier"
            entry["amount"] += bill["net"]
            entry["bills"] += 0 if bill["is_return"] else 1
    total = sum(entry["amount"] for entry in spend.values())
    ranked = sorted(
        ({**entry, "share": entry["amount"] / total * 100 if total else 0} for entry in spend.values()),
        key=lambda supplier: supplier["amount"], reverse=True,
    )
    return {"top": ranked[:limit], "total": total, "count": len(ranked)}


# --------------------------------------------------------------------------


def build_insights(period, data, settings=None, today=None):
    """Every insight section for one dashboard period.

    today defaults to the latest sale, so periods end on the latest bill
    even when the data is a day or two old.
    """
    settings = settings or Settings()
    today = today or latest_date(data) or datetime.now().date()
    lines = data["sales_lines"]
    bills = data["bills"]
    last_bought = last_purchases(data["purchase_lines"])

    credit_bills = defaultdict(list)
    for bill in bills:
        if bill["credit"] and not bill["is_return"]:
            credit_bills[bill["party_id"]].append(bill)
    purchase_bills = defaultdict(list)
    for bill in data["purchases"]:
        if not bill["is_return"]:
            purchase_bills[bill["party_id"]].append(bill)

    insights = {
        "today": today,
        "comparison": period_comparison(bills, lines, period, today),
        "weekdays": weekday_pattern(bills),
        "reorder": reorder_alerts(data["items"], lines, last_bought, today, settings),
        "stock": stock_health(data["items"], lines, last_bought, today, settings),
        "margins": margin_watch(lines, period, today, settings),
        "customers": customer_insights(bills, period, today),
        "receivables": outstanding(data["receivables"], credit_bills, today),
        "payables": outstanding(data["payables"], purchase_bills, today),
        "suppliers": supplier_spend(data["purchases"], period, today),
        "settings": {
            "reorder_cover_days": settings.reorder_cover_days,
            "reorder_target_days": settings.reorder_target_days,
            "reorder_min_sale_days": settings.reorder_min_sale_days,
            "dead_stock_days": settings.dead_stock_days,
        },
    }

    receivable_over_30 = sum(b["amount"] for b in insights["receivables"]["buckets"][1:])
    insights["attention"] = {
        "reorder": len(insights["reorder"]["items"]),
        "out_of_stock": sum(1 for a in insights["reorder"]["items"] if a["stock"] <= 0),
        "loss_items": len(insights["margins"]["loss_items"]),
        "loss_total": insights["margins"]["loss_total"],
        "receivable": insights["receivables"]["total"],
        "receivable_over_30": receivable_over_30,
        "dead_value": insights["stock"]["dead_value"],
        "dead_count": insights["stock"]["dead_count"],
    }
    return insights
