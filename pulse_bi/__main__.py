"""Command line for Pulse BI. Every command works on one customer.

    python -m pulse_bi [--customer NAME] check              read the source and show a summary
    python -m pulse_bi [--customer NAME] quote "TEXT"       answer an enquiry as the web page would
    python -m pulse_bi [--customer NAME] whatsapp "TEXT" --sender NUMBER
                                                            the WhatsApp reply (None = no reply)
    python -m pulse_bi [--customer NAME] serve [--port N]   web server (search page, live dashboard)
    python -m pulse_bi [--customer NAME] publish [--no-deploy]
                                                            static dashboard (and upload if configured)
    python -m pulse_bi [--customer NAME] alerts [--dry-run] staff alert email

NAME is a file in customers/ (default: demo, or PULSE_CUSTOMER).
"""

import argparse
import sys

from .config import Customer


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m pulse_bi", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--customer", help="customer config name or path (default: demo)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    quote = commands.add_parser("quote")
    quote.add_argument("text")
    whatsapp = commands.add_parser("whatsapp")
    whatsapp.add_argument("text")
    whatsapp.add_argument("--sender", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=5000)
    publish = commands.add_parser("publish")
    publish.add_argument("--no-deploy", action="store_true")
    alerts = commands.add_parser("alerts")
    alerts.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    customer = Customer.load(args.customer)

    if args.command == "check":
        from .engine import insights as engine
        from .engine.formatting import inr
        from .model import validate
        data = validate(customer.source.load())
        summary = engine.sales_summary(data["bills"])
        print(f"{customer.business_name}: {customer.source.label}")
        print(f"  {len(data['items'])} items, {summary['sales_invoice_count']} bills "
              f"{summary['sales_first_date']} to {summary['sales_last_date']}, "
              f"net sales {customer.currency_symbol}{inr(summary['sales_net_amount'])}")
        print(f"  channels: {', '.join(k for k, v in customer.channels.items() if v) or 'none'}")

    elif args.command == "quote":
        from .channels.text import render_text
        print(render_text(customer.quoter.quote(args.text), customer.currency_symbol))

    elif args.command == "whatsapp":
        from .channels.whatsapp import handle_message
        print(handle_message(args.text, args.sender, customer))

    elif args.command == "serve":
        from .web import create_app
        create_app(customer).run(host=args.host, port=args.port, debug=False)

    elif args.command == "publish":
        from .dashboard.publish import deploy, save_pages
        from .web import create_app
        site = save_pages(customer, create_app(customer))
        print(f"Saved the dashboard to {site}")
        if not args.no_deploy:
            deploy(customer, site)

    elif args.command == "alerts":
        from .alerts.email import run
        subject, preview = run(customer, dry_run=args.dry_run)
        print(subject)
        print(f"Preview: {preview}" + (" (dry run: nothing sent)" if args.dry_run else ""))


if __name__ == "__main__":
    sys.exit(main())
