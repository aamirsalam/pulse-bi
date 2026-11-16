"""Odoo: not written yet.

To write it, fill load() with a BusinessData dict (pulse_bi.model), read
through Odoo's external API with a user that can only read. Check every
mapping against a real database before trusting the figures.

Things to decide when writing it:
- Which Odoo version and edition the customer runs (models and fields
  differ between versions).
- Stock: quantity on hand per product (and per warehouse, if they have
  several), and a cost per unit before tax.
- Sales: posted customer invoices and credit notes (returns) with their
  lines, before/after tax amounts, cancelled ones left out. Decide whether
  sales orders or invoices count as the sale.
- Customers and suppliers: amounts still owed on posted invoices and bills.
- Purchases: posted vendor bills and refunds with their lines.

[source]
type = "odoo"
# url, database and user here; the password or API key in an environment variable
"""

from .base import Source, SourceNotReady


class OdooSource(Source):
    label = "Odoo"

    def load(self):
        raise SourceNotReady("The Odoo source isn't written yet: see pulse_bi/sources/odoo.py.")
