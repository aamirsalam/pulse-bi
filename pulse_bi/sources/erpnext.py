"""ERPNext / Frappe: not written yet.

To write it, fill load() with a BusinessData dict (pulse_bi.model), read
through the site's REST API with an API key for a user that can only read.
Check every mapping against a real site before trusting the figures.

Things to decide when writing it:
- Stock: actual quantity per item (summed over warehouses, or one
  warehouse), and a cost per unit before tax (valuation rate).
- Sales: submitted Sales Invoices and their returns (credit notes) with
  their items, cancelled ones left out, invoice-level discounts spread over
  the lines so they add up to the grand total.
- Customers and suppliers: outstanding amounts on submitted invoices.
- Purchases: submitted Purchase Invoices and returns with their items.

[source]
type = "erpnext"
# site url here; the API key and secret in environment variables
"""

from .base import Source, SourceNotReady


class ERPNextSource(Source):
    label = "ERPNext"

    def load(self):
        raise SourceNotReady("The ERPNext source isn't written yet: see pulse_bi/sources/erpnext.py.")
