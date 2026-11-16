"""Daily alert email for shop staff.

Checks the data and emails staff about:
- items out of stock or running low (the dashboard's Reorder Alerts rules)
  and items with negative stock;
- bill lines not reported before that were sold below cost or under the
  low-margin threshold, priced far from the item's usual selling price
  (often a mistyped quantity or rate), or for items with no purchase cost.

It leaves out money owed, supplier balances and sales totals: those are
for the owner's dashboard.

Each bill is reported once: reported bills are kept in the state file
(output/<customer>/alerts_state.json by default). Today's bills wait for
tomorrow's email, since the day isn't finished. On the first run only
yesterday's bills are checked, so the first email isn't a backlog. Bills
older than STATE_KEEP_DAYS are dropped from the state and not checked again.

Config and environment:

[alerts]
recipients = ["staff@example.com"]   # or PULSE_ALERT_TO (comma-separated)
smtp_host = "smtp.gmail.com"         # default; SSL on port 465
stale_hours = 36                     # warn when the data is older than this

PULSE_ALERT_EMAIL         the address it sends from
PULSE_ALERT_APP_PASSWORD  its password (for Gmail, an app password)
"""

import html
import json
import os
import smtplib
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from ..engine import insights as engine
from ..engine.formatting import inr

UNUSUAL_PRICE_LOW = 0.5      # flag a price under half the item's usual price
UNUSUAL_PRICE_HIGH = 2.0     # ... or over double it
UNUSUAL_PRICE_MIN_SALES = 3  # usual price needs at least this many other bills
STATE_KEEP_DAYS = 120        # forget reported bills older than this


# --------------------------------------------------------------------------
# Checks


def usual_prices(lines, ignore_before):
    """Selling prices (before tax, per unit) of each item, per bill line."""
    prices = defaultdict(list)
    for line in lines:
        if line["qty"] > 0 and (ignore_before is None or line["date"] >= ignore_before):
            prices[line["item_code"]].append((line["bill_id"], line["sales_ex_tax"] / line["qty"]))
    return prices


def check_bills(lines, new_ids, settings):
    """Problems on the bill lines that haven't been reported yet."""
    prices = usual_prices(lines, settings.margin_ignore_before)
    below_cost, low_margin, unusual, no_cost = [], [], [], []

    for line in lines:
        if line["bill_id"] not in new_ids or line["qty"] <= 0:
            continue
        price = line["sales_ex_tax"] / line["qty"]
        row = {
            "date": line["date"], "bill": line["bill_no"], "customer": engine.customer_label(line),
            "item": line["product"], "qty": line["qty"], "price": price, "cost": line["unit_cost"],
        }

        others = [p for bill_id, p in prices[line["item_code"]] if bill_id != line["bill_id"]]
        if len(others) >= UNUSUAL_PRICE_MIN_SALES:
            usual = statistics.median(others)
            if usual > 0 and not (UNUSUAL_PRICE_LOW <= price / usual <= UNUSUAL_PRICE_HIGH):
                unusual.append({**row, "usual": usual, "times": price / usual})

        profit = engine.line_profit(line)
        if profit is None:
            no_cost.append(row)
            continue
        margin = profit / line["sales_ex_tax"] * 100 if line["sales_ex_tax"] else None
        row.update(profit=profit, margin=margin)
        if profit < 0:
            below_cost.append(row)
        elif margin is not None and margin < settings.low_margin_percent:
            low_margin.append(row)

    below_cost.sort(key=lambda row: row["profit"])
    low_margin.sort(key=lambda row: row["margin"])
    unusual.sort(key=lambda row: abs(row["times"] - 1), reverse=True)
    return {"below_cost": below_cost, "low_margin": low_margin, "unusual": unusual, "no_cost": no_cost}


# --------------------------------------------------------------------------
# Which bills are new


def load_state(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def new_bills(lines, state, today, ignore_before=None):
    """Bill ids to check now: not yet reported and dated before today."""
    by_id = {line["bill_id"]: line["date"] for line in lines}
    if state is None:
        yesterday = today - timedelta(days=1)  # first run: just yesterday's bills
        return {bill_id for bill_id, day in by_id.items() if day == yesterday}

    reported = set(state.get("reported", {}))
    oldest = today - timedelta(days=STATE_KEEP_DAYS)
    if ignore_before:
        oldest = max(oldest, ignore_before)
    return {bill_id for bill_id, day in by_id.items() if oldest <= day < today and bill_id not in reported}


def save_state(path, state, lines, checked_ids, today):
    """Remember checked bills, and every older bill on a first run."""
    reported = dict((state or {}).get("reported", {}))
    for line in lines:
        if line["bill_id"] in checked_ids or (state is None and line["date"] < today):
            reported[line["bill_id"]] = line["date"].isoformat()
    cutoff = (today - timedelta(days=STATE_KEEP_DAYS)).isoformat()
    reported = {bill_id: day for bill_id, day in reported.items() if day >= cutoff}

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"last_sent": datetime.now().isoformat(timespec="seconds"),
                                "reported": reported}, indent=1), encoding="utf-8")


# --------------------------------------------------------------------------
# Email


def qty_text(value):
    return ("%.3f" % value).rstrip("0").rstrip(".")


def e(value):
    return html.escape(str(value))


CELL = "padding:6px 8px;border-bottom:1px solid #e2e8f0;vertical-align:top;"
HEAD = CELL + "text-align:left;background:#f1f5f9;font-size:12px;color:#475569;"
RIGHT = "text-align:right;white-space:nowrap;"


def table(headers, rows, right_from=None):
    """HTML table; columns from index right_from are right-aligned."""
    def style(index, base):
        return base + (RIGHT if right_from is not None and index >= right_from else "")
    head = "".join(f'<th style="{style(i, HEAD)}">{e(h)}</th>' for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(f'<td style="{style(i, CELL)}">{cell}</td>' for i, cell in enumerate(row)) + "</tr>"
        for row in rows
    )
    return ('<table style="border-collapse:collapse;width:100%;font-size:13px;margin:6px 0 4px;">'
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")


def section(title, note, content, count):
    return (f'<h2 style="font-size:16px;margin:26px 0 4px;color:#1f2937;">{e(title)}'
            f' <span style="color:#64748b;font-weight:normal;">({count})</span></h2>'
            f'<p style="margin:0 0 6px;color:#64748b;font-size:12px;">{note}</p>{content}')


def bill_cell(row):
    return (f"{e(row['bill'])}<br><span style=\"color:#64748b;font-size:11px;white-space:nowrap;\">"
            f"{row['date']:%d %b}</span>")


def build_email(customer, data, reorder, problems, checked_dates, today):
    settings = customer.settings
    stale_hours = customer.section("alerts").get("stale_hours", 36)

    def money(value, decimals=2):
        return customer.currency_symbol + inr(value, decimals)

    items = reorder["items"]
    out_of_stock = [a for a in items if a["stock"] <= 0]
    low_stock = [a for a in items if a["stock"] > 0]
    negative = sorted((i for i in data["items"] if i["stock"] < 0), key=lambda i: i["stock"])
    bill_issues = sum(len(problems[k]) for k in ("below_cost", "low_margin", "unusual"))

    summary = []
    if out_of_stock:
        summary.append(f"{len(out_of_stock)} out of stock")
    if low_stock:
        summary.append(f"{len(low_stock)} running low")
    if bill_issues:
        summary.append(f"{bill_issues} bill line{'s' if bill_issues != 1 else ''} to check")
    subject = f"{customer.business_name} alerts {today:%d %b}: " + (", ".join(summary) or "all clear")

    parts = []
    if checked_dates:
        first, last = min(checked_dates), max(checked_dates)
        period = f"{first:%d %b}" if first == last else f"{first:%d %b} – {last:%d %b}"
        bills_text = f"Bills checked: {period} ({problems['bill_count']} bills)."
    else:
        bills_text = "No new bills to check since the last email."
    checked_at = data["checked_at"]
    stale = (datetime.now(checked_at.tzinfo) - checked_at).total_seconds() / 3600 > stale_hours
    parts.append(
        '<p style="margin:0 0 4px;font-size:14px;">' + e(bills_text) + "</p>"
        f'<p style="margin:0;font-size:12px;color:{"#b91c1c" if stale else "#64748b"};">'
        f"Data as of {checked_at:%d %b %Y, %I:%M %p}"
        + (" — this is old: check that the accounts data is being updated." if stale else "") + "</p>"
    )

    def reorder_rows(rows):
        out = []
        for a in rows:
            bought = a["last_bought"]
            last = (f"{e(bought['supplier'])}<br><span style=\"color:#64748b;font-size:11px;\">"
                    f"{bought['date']:%d %b}" + (f" · {money(bought['rate'])}" if bought["rate"] else "")
                    + "</span>") if bought else "–"
            left = "Out" if a["stock"] <= 0 else f"~{a['days_left']:.0f} days"
            out.append([e(a["name"]), qty_text(a["stock"]), left, qty_text(a["sold"]), f"~{a['suggested']}", last])
        return out

    if items:
        parts.append(section(
            "Stock to reorder",
            f"Out of stock, or under {settings.reorder_cover_days} days left at the last "
            f"{reorder['window_days']} days' sales pace. Order qty tops stock up to "
            f"{settings.reorder_target_days} days of sales.",
            table(["Item", "Stock", "Left", f"Sold {reorder['window_days']}d", "Order", "Last bought from"],
                  reorder_rows(items), right_from=1),
            len(items),
        ))

    if problems["below_cost"]:
        parts.append(section(
            "Sold below cost",
            "Price charged is under the purchase cost (both before tax). Check the rate on the bill, "
            "and the item's purchase rate in the accounts system.",
            table(["Bill", "Customer", "Item", "Qty", "Price", "Cost", "Loss"],
                  [[bill_cell(r), e(r["customer"]), e(r["item"]), qty_text(r["qty"]), money(r["price"]),
                    money(r["cost"]), f'<span style="color:#b91c1c;">−{money(-r["profit"], 0)}</span>']
                   for r in problems["below_cost"]], right_from=3),
            len(problems["below_cost"]),
        ))

    if problems["low_margin"]:
        # One row per item: the same item is usually priced the same way on
        # every bill, so listing each line repeats it.
        grouped = {}
        for r in problems["low_margin"]:
            g = grouped.setdefault(r["item"], {"item": r["item"], "bills": [], "qty": 0.0,
                                               "sales": 0.0, "cost": r["cost"], "profit": 0.0})
            if r["bill"] not in g["bills"]:
                g["bills"].append(r["bill"])
            g["qty"] += r["qty"]
            g["sales"] += r["price"] * r["qty"]
            g["profit"] += r["profit"]
        groups = sorted(grouped.values(), key=lambda g: g["profit"] / g["sales"] if g["sales"] else 0)
        parts.append(section(
            f"Low margin (under {settings.low_margin_percent:g}%)",
            "Sold above cost but with little profit. If an item is here every day, its selling price may need raising.",
            table(["Item", "Bills", "Qty", "Avg price", "Cost", "Margin"],
                  [[e(g["item"]), e(", ".join(str(b) for b in g["bills"])), qty_text(g["qty"]),
                    money(g["sales"] / g["qty"]), money(g["cost"]),
                    f"{g['profit'] / g['sales'] * 100:.1f}%" if g["sales"] else "–"]
                   for g in groups], right_from=2),
            len(groups),
        ))

    if problems["unusual"]:
        parts.append(section(
            "Unusual price — check the bill",
            "Price per unit is under half or over double what this item usually sells for. "
            "Often the quantity or rate was typed wrong, which also throws off the stock count.",
            table(["Bill", "Customer", "Item", "Qty", "Price", "Usual"],
                  [[bill_cell(r), e(r["customer"]), e(r["item"]), qty_text(r["qty"]),
                    money(r["price"]), money(r["usual"])] for r in problems["unusual"]], right_from=3),
            len(problems["unusual"]),
        ))

    if problems["no_cost"]:
        parts.append(section(
            "Sold with no purchase cost",
            "These items have no purchase cost in the accounts system, so their margin "
            "can't be checked. Enter the item's purchase rate.",
            table(["Bill", "Item", "Qty", "Price"],
                  [[bill_cell(r), e(r["item"]), qty_text(r["qty"]), money(r["price"])]
                   for r in problems["no_cost"]], right_from=2),
            len(problems["no_cost"]),
        ))

    if negative:
        parts.append(section(
            "Negative stock",
            "The accounts show less than zero in stock. Usually a purchase bill hasn't been entered yet, "
            "or a sale was billed under the wrong item.",
            table(["Code", "Item", "Stock"],
                  [[e(i["code"]), e(i["name"]), f'<span style="color:#b91c1c;">{qty_text(i["stock"])}</span>']
                   for i in negative], right_from=2),
            len(negative),
        ))

    if len(parts) == 1:
        parts.append('<p style="margin-top:20px;">Nothing needs attention today.</p>')

    body = (
        '<div style="font-family:Arial,Helvetica,sans-serif;color:#1f2937;max-width:760px;">'
        f'<h1 style="font-size:20px;margin:0 0 8px;">{e(customer.business_name)} — daily alerts</h1>'
        + "".join(parts)
        + '<p style="margin-top:28px;font-size:11px;color:#94a3b8;">Sent automatically by Pulse BI. '
          "Each bill is reported once. Prices and costs are before tax.</p></div>"
    )
    return subject, body


def send(customer, subject, body):
    sender = os.environ.get("PULSE_ALERT_EMAIL")
    password = os.environ.get("PULSE_ALERT_APP_PASSWORD")
    if not sender or not password:
        raise SystemExit("Set the PULSE_ALERT_EMAIL and PULSE_ALERT_APP_PASSWORD environment variables first.")
    config = customer.section("alerts")
    recipients = [r.strip() for r in os.environ.get("PULSE_ALERT_TO", "").split(",") if r.strip()]
    recipients = recipients or config.get("recipients") or [sender]

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{customer.business_name} Alerts <{sender}>"
    message["To"] = ", ".join(recipients)
    message.set_content("This email needs an HTML-capable mail app.")
    message.add_alternative(body, subtype="html")
    with smtplib.SMTP_SSL(config.get("smtp_host", "smtp.gmail.com"), config.get("smtp_port", 465), timeout=60) as server:
        server.login(sender, password.replace(" ", ""))
        server.send_message(message)
    return recipients


def run(customer, dry_run=False, today=None, force=False):
    """Check, build the email, and (unless dry_run) send it and remember the bills.
    Returns (subject, preview path), or (None, None) when an email already
    went out today (so a scheduler can run this hourly; force sends anyway)."""
    today = today or date.today()
    state_path = Path(customer.section("alerts").get("state_file") or customer.output_dir("alerts_state.json"))
    state = load_state(state_path)
    if not dry_run and not force and state and state.get("last_sent", "")[:10] == today.isoformat():
        return None, None

    data = customer.source.load()
    bill_lines = [line for line in data["sales_lines"] if not line["is_return"]]

    # Reorder counts back from the latest bill, like the dashboard.
    latest = engine.latest_date(data) or today
    reorder = engine.reorder_alerts(data["items"], data["sales_lines"],
                                    engine.last_purchases(data["purchase_lines"]), latest, customer.settings)

    ids = new_bills(bill_lines, state, today, customer.settings.margin_ignore_before)
    problems = check_bills(bill_lines, ids, customer.settings)
    problems["bill_count"] = len(ids)
    checked_dates = {line["date"] for line in bill_lines if line["bill_id"] in ids}

    subject, body = build_email(customer, data, reorder, problems, checked_dates, today)
    preview = customer.output_dir("alert_preview.html")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_text(f"<!DOCTYPE html><meta charset='utf-8'><title>{e(subject)}</title>{body}", encoding="utf-8")

    if not dry_run:
        send(customer, subject, body)
        save_state(state_path, state, bill_lines, ids, today)
    return subject, preview
