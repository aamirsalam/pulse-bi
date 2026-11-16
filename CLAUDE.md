# CLAUDE.md

Guidance for Claude Code in this repository. README.md has the overview and commands.

## Rules

- `pulse_bi/model.py` is the contract between sources and everything else. Downstream code
  (engine, quote, channels, dashboard, alerts) never reads an accounting system directly; a
  new field goes into the contract, every source and `validate()` together.
- All system-specific knowledge stays in its source (e.g. `pulse_bi/sources/lux/source.py`:
  the CGST-half tax fields, the FormNo join, bill-level discount scaling, account groups,
  typed-name cleanup). Don't leak it into the engine or templates.
- The quote safety rules live in `pulse_bi/quote/service.py`, not in channels: never guess a
  product (`review`/`no_match` need a person), withhold prices when stock is missing or
  negative or the rate is missing or ≤ 0, flag shortages. Price options are rate ×
  (1 + markup%), rounded half-up to 2 dp with Decimal.
- WhatsApp is staff-only: `handle_message` replies only to `[whatsapp] allowed_senders`
  (empty by default). Don't make it answer customers without the owner's decision and a
  customer-safe reply format.
- Never commit customer data or secrets: real `customers/*.toml`, databases (`*.mdb`,
  `*.sqlite`), exports, `output/`, state files. Secrets come from environment variables.
  `[publish] cloudflare_worker` has no default on purpose.
- Tally, Odoo and ERPNext sources are placeholders. Don't fill them from memory: map them
  against a real system and check totals against its own reports.
- Thresholds are per customer (`[insights]`, `pulse_bi.engine.insights.Settings`), not constants.

## Commands

```bash
pytest                                   # tests (demo data)
python -m pyflakes pulse_bi tests tools  # lint
python -m pulse_bi --customer demo check|quote "..."|whatsapp "..." --sender N|serve|publish --no-deploy|alerts --dry-run
python tools/make_demo_data.py           # regenerate demo_data/ (tests rely on its figures)
```

Templates (`pulse_bi/templates/`): one per dashboard section, included by `dashboard.html`;
every colour and font is a token in its `:root` block. `business_name`, `cur` (currency
symbol), `tax_name`, `source_label` and `web_enabled` are Jinja globals set in `pulse_bi/web.py`.
