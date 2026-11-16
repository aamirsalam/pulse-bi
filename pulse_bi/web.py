"""The web server for one customer: the stock search page and the live
dashboard, each switched on or off in the customer's config.

    python -m pulse_bi --customer demo serve
"""

from flask import Flask, abort, current_app, request

from .dashboard.render import PERIODS, render_dashboard, render_error
from .engine.formatting import inr


def create_app(customer):
    app = Flask(__name__)
    app.config["CUSTOMER"] = customer
    app.add_template_filter(inr, "inr")
    app.jinja_env.globals.update(
        business_name=customer.business_name,
        cur=customer.currency_symbol,
        tax_name=customer.tax_name,
        source_label=customer.source.label,
        web_enabled=bool(customer.channels.get("web")),
    )

    if customer.channels.get("web"):
        from .channels.web import blueprint
        app.register_blueprint(blueprint)

    @app.route("/dashboard")
    def dashboard():
        if not customer.dashboard.get("local"):
            abort(404)
        period = request.args.get("period", "all")
        if period not in PERIODS:
            period = "all"
        try:
            return render_dashboard(current_app.config["CUSTOMER"], period)
        except Exception:
            app.logger.exception("Dashboard data query failed")
            return render_error("Unable to read the accounts data. Check the server terminal."), 500

    return app
