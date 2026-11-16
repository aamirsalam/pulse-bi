"""Tally Prime: not written yet.

To write it, fill load() with a BusinessData dict (pulse_bi.model). Check
every mapping against a real Tally company before trusting the figures;
the Lux source's notes show the kind of surprises to look for (tax split
over two fields, totals not on the lines, balances not kept up to date).

Things to decide when writing it:
- How to read Tally: its XML/JSON interface on the Tally machine (it must
  be running with the company open and the port enabled), or exports.
- Stock: closing quantity per stock item, and a cost per unit before tax.
- Sales: sales vouchers and credit notes (returns) with their inventory
  lines, cancelled vouchers left out, voucher-level discounts spread over
  the lines so they add up to the voucher total.
- Customers and suppliers: ledgers under Sundry Debtors / Sundry Creditors
  and their closing balances; cash sales' party names.
- Purchases: purchase vouchers and debit notes with their inventory lines.

[source]
type = "tally"
# connection settings go here, secrets in environment variables
"""

from .base import Source, SourceNotReady


class TallySource(Source):
    label = "Tally Prime"

    def load(self):
        raise SourceNotReady("The Tally Prime source isn't written yet: see pulse_bi/sources/tally.py.")
