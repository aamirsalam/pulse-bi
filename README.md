# Pulse BI

Stock quotes and business insights for small trading businesses, on top of
whatever accounting system the business already uses.

- **Quotes**: match a customer's enquiry ("20 pcs 1 1/2 x 1 angle") to stock
  and show price options, never guessing a product. Answered on a **web
  page** or over **WhatsApp**, switchable per customer.
- **Owner dashboard**: sales against the previous period, margins, sales
  below cost, reorder alerts, stock not moving, customers, money owed and
  owed to suppliers. A live page, or a static site behind a password.
- **Staff alert email**: daily stock to reorder and problem bill lines.
- **Data sources**, picked per customer: LUX (Access) and a demo/CSV source
  work today; Tally Prime, Odoo and ERPNext are documented placeholders.

## Quick start

Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m pulse_bi check                                   # read the demo data
python -m pulse_bi quote "20 pcs 1 1/2 x 1"                # a quote as text
python -m pulse_bi whatsapp "steel hinge" --sender "+91 90000 00001"
python -m pulse_bi serve                                   # http://127.0.0.1:5000 and /dashboard
python -m pulse_bi publish --no-deploy                     # static dashboard in output/demo/site
python -m pulse_bi alerts --dry-run                        # output/demo/alert_preview.html (at most one real send a day)
pytest
```

Everything runs on the made-up data in `demo_data/` (a small hardware shop,
regenerated with `python tools/make_demo_data.py`). Pick another customer
with `--customer <name>` or `PULSE_CUSTOMER`.

## How it fits together

```
accounting system ──> source ──> BusinessData ──> insights ──> dashboard, alert email
   (LUX, Tally...)   (sources/)   (model.py)      (engine/)
                         │
                         └─> catalogue ──> quote core ──> web page / WhatsApp
                                           (quote/)       (channels/)
```

| Path | What |
|---|---|
| `pulse_bi/model.py` | **The data contract.** Every source returns one `BusinessData` dict; nothing downstream reads an accounting system directly. Conventions (tax, returns, discounts, walk-ins) are in its docstring; `validate()` checks a dict. |
| `pulse_bi/sources/` | One adapter per system. `lux/` holds all the LUX SQL and rules; `demo.py` reads CSVs; `tally.py`, `odoo.py`, `erpnext.py` raise `SourceNotReady` with notes on what to map. |
| `pulse_bi/engine/` | Insights from the contract, pure Python. |
| `pulse_bi/quote/` | Matching, pricing and the safety rules, with no channel code. `enquiry_parser.py` optionally reads free-text enquiries with a local AI model (off by default). |
| `pulse_bi/channels/` | `web.py` (search page), `whatsapp.py` (`handle_message`), `text.py` (chat replies). |
| `pulse_bi/dashboard/` | Dashboard pages; `publish.py` saves and uploads the static site. |
| `pulse_bi/alerts/` | Staff alert email. |
| `pulse_bi/config.py` | Loads `customers/<name>.toml`. |
| `customers/` | `demo.toml` and `lux.example.toml`. Real customer files are git-ignored. |
| `deploy/worker.js` | Password check for a published dashboard on Cloudflare Workers. |
| `tools/` | Demo data generator; LUX stock report importer. |

## Customers

One TOML file per customer in `customers/` chooses:

- `[source] type`: `lux`, `demo`, `tally`, `odoo` or `erpnext`, with that
  source's settings;
- `[channels]`: `web` and/or `whatsapp`;
- `[whatsapp] allowed_senders`: staff numbers allowed to ask;
- `[quote] markups`: the price options;
- `[insights]`: thresholds (low margin %, reorder cover, dead stock days...);
- `[alerts] recipients` and `[publish] cloudflare_worker` (none by default,
  so a test run never uploads anywhere).

Secrets never go in these files, only environment variables:
`PULSE_ALERT_EMAIL`, `PULSE_ALERT_APP_PASSWORD` (alert email),
`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` (publishing). Customer data,
databases, exports and run state stay out of git (see `.gitignore`).

## WhatsApp integration

Start here: [docs/whatsapp-integration.md](docs/whatsapp-integration.md) (partial checkout, setup, Meta test number, where the code goes).

The quoting side is done; the integration is the transport around this call:

```python
from pulse_bi.config import Customer
from pulse_bi.channels.whatsapp import handle_message

customer = Customer.load("demo")
reply = handle_message(text, sender_number, customer)   # str, or None = don't reply
```

What's left to build:

1. A webhook that receives incoming messages from the WhatsApp Business
   Platform (directly from Meta or through a provider), verifies that the
   request really comes from it, and extracts the text and sender number.
2. Sending `reply` back to the sender.
3. Registering the webhook in `pulse_bi/web.py` only when
   `customer.channels["whatsapp"]` is on, with its secrets in environment
   variables.

Keep these as they are:

- **Staff only.** `handle_message` answers only numbers in
  `[whatsapp] allowed_senders`, which is empty by default. A quote shows the
  base rate (cost-based) and "possible matches" that need a person to
  confirm, so it isn't fit to send to customers as is. Answering customers
  directly needs a customer-safe reply format and the owner's decision.
- **The safety rules stay in `pulse_bi/quote/service.py`**, not in the channel:
  never guess a product, withhold prices when stock is missing or negative
  or the rate is missing or zero, flag shortages.
- Don't log full replies: they contain prices.

`python -m pulse_bi whatsapp "..." --sender "..."` shows exactly what a
message would get back, without WhatsApp.

Free-text messages ("20 sheet venam, 8 adi x 4 adi") match better through
`pulse_bi/quote/enquiry_parser.py`: `request_flow(message, customer.quoter,
customer.section("quote").get("llm", {}))` quotes the message directly when it
names an item exactly, otherwise asks a local Ollama model for the items and
quotes each. It's off unless `[quote.llm] enabled = true`, and needs Ollama
running with the model; `handle_message` doesn't use it yet.

## Quote prices

A quote's options are the item's rate plus each markup, so the rate must be
the cost **including tax** (or a price list's base). The contract's
`unit_cost` is before tax, so sources don't use it directly: by default
prices are withheld. The LUX source prices from its stock report export
(`P/Rate+Tax`, via `tools/import_stock_report.py` and `[source]
catalogue_csv`); the demo source adds `[source] tax_percent` to the cost. A
new source should supply its system's tax-inclusive cost or price list in
`load_catalogue()`.

## Adding an accounting system

1. Subclass `Source` in `pulse_bi/sources/<system>.py` and return a
   `BusinessData` dict from `load()`, following the conventions in
   `pulse_bi/model.py`. Override `load_catalogue()` if the system has a
   better price base for quotes than cost before tax.
2. Register it in `SOURCES` in `pulse_bi/sources/__init__.py`.
3. Test it with `validate()`, then compare the dashboard against the
   system's own reports (sales total, stock of a few items, a customer's
   balance) for a real company before trusting it. The LUX source's
   docstring shows the kind of surprises to expect.

## Status

Working: the LUX and demo sources, the insights, the dashboard (live and
published), the alert email, quotes on the web page, WhatsApp's
`handle_message`, and the optional enquiry parser. On a SQLite copy of real
LUX data, every dashboard figure, the alert email's checks and the pages
match the original tool exactly; reading the .mdb directly on Windows
(pyodbc) uses the same SQL but hasn't been run from this repo yet.

Open:

- Tally Prime, Odoo and ERPNext sources aren't written yet.
- The WhatsApp webhook and sending (above).
- Nothing schedules `publish` or `alerts` yet, and nothing downloads a
  database snapshot: run them from a scheduler (cron, Task Scheduler, a CI
  job). `alerts` sends at most one email a day, so running it hourly is safe.
- A quote treats an item whose full name appears inside a longer enquiry as
  an exact match; it should probably ask for review instead.
- The live dashboard (`serve`) has no password; keep it on a trusted
  network or put it behind one.
- LUX starts a new database file each financial year, which resets history.
