"""Web channel: the stock search page ("/"), over the same quoting core
as WhatsApp. Switched on per customer with [channels] web = true."""

from flask import Blueprint, current_app, render_template, request

blueprint = Blueprint("web_quotes", __name__)


@blueprint.route("/", methods=["GET"])
def search():
    customer = current_app.config["CUSTOMER"]
    query = request.args.get("q", "").strip()
    result, error = None, None
    if query:
        try:
            result = customer.quoter.quote(query)
        except Exception:
            current_app.logger.exception("Stock search failed")
            error = "Unable to load the stock list. Check the server terminal."
    return render_template(
        "index.html",
        query=query,
        results={"status": result["status"], "matches": result["products"]} if result else None,
        products=result["products"] if result else [],
        error=error,
    )
