"""Owner dashboard: one page per period from a BusinessData dict.

render_dashboard() is used by the live page (pulse_bi.web, /dashboard) and
by the published static site (pulse_bi.dashboard.publish).
"""

from flask import render_template

from ..engine import insights as engine

PERIODS = engine.PERIODS


def page_context(customer, data, period):
    items = data["items"]
    negative = sorted((item for item in items if item["stock"] < 0), key=lambda item: item["stock"])
    latest = engine.latest_date(data)
    return {
        "total_items": len(items),
        "negative_stock": len(negative),
        "zero_stock": sum(1 for item in items if item["stock"] == 0),
        "positive_stock": sum(1 for item in items if item["stock"] > 0),
        "negative_items": negative,
        "stock_items": items,
        "database_checked_at": data["checked_at"],
        "daily_sales": engine.daily_sales(data["bills"], data["sales_lines"]),
        "top_products": engine.top_products(data["sales_lines"], period, latest) if latest else [],
        "top_products_period": period,
        "insights": engine.build_insights(period, data, customer.settings, today=latest) if latest else None,
        **engine.sales_summary(data["bills"]),
        **engine.summarise_profit(data["sales_lines"]),
    }


def render_dashboard(customer, period, data=None, static_site=False):
    data = data or customer.source.load()
    return render_template("dashboard.html", error=None, static_site=static_site,
                           **page_context(customer, data, period))


def render_error(message):
    return render_template(
        "dashboard.html", error=message, static_site=False, database_checked_at=None,
        total_items=0, positive_stock=0, zero_stock=0, negative_stock=0, negative_items=[],
        sales_invoice_count=0, sales_first_date=None, sales_last_date=None, sales_net_amount=0,
        daily_sales=[], top_products=[], top_products_period="all", insights=None,
    )
