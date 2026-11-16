"""Save the dashboard as static pages, and optionally upload them to a
password-protected Cloudflare Worker (deploy/worker.js).

The Worker is only deployed when the customer config names one; there is
no default, so a test run can't overwrite anyone's live dashboard:

[publish]
cloudflare_worker = "acme-dashboard"     # Worker name; leave out to only save pages

Needs wrangler (npm install -g wrangler) and the CLOUDFLARE_API_TOKEN and
CLOUDFLARE_ACCOUNT_ID environment variables. Set the password once with
`wrangler secret put DASHBOARD_PASSWORD --name <worker>` (user "owner").
"""

import json
import shutil
import subprocess
from pathlib import Path

from .render import PERIODS, render_dashboard

REPO = Path(__file__).resolve().parents[2]


def page_name(period):
    return "index.html" if period == "all" else f"{period}.html"


def save_pages(customer, app):
    """Render every period from one read of the data, then write them, so
    a data error never leaves half a site."""
    data = customer.source.load()
    with app.test_request_context():
        pages = {page_name(p): render_dashboard(customer, p, data=data, static_site=True) for p in PERIODS}

    site = customer.output_dir("site")
    if site.exists():
        shutil.rmtree(site)
    site.mkdir(parents=True)
    for name, html in pages.items():
        (site / name).write_text(html, encoding="utf-8")
    return site


def deploy(customer, site):
    worker = customer.section("publish").get("cloudflare_worker")
    if not worker:
        print("No [publish] cloudflare_worker in the customer config: pages saved, not uploaded.")
        return False
    wrangler = shutil.which("wrangler.cmd") or shutil.which("wrangler")
    if wrangler is None:
        raise SystemExit("wrangler not found - install it with: npm install -g wrangler")

    config = customer.output_dir("wrangler.json")
    config.write_text(json.dumps({
        "name": worker,
        "main": str(REPO / "deploy" / "worker.js"),
        "compatibility_date": "2026-11-03",
        "workers_dev": True,
        "preview_urls": False,
        "assets": {"directory": str(site), "binding": "ASSETS", "run_worker_first": True},
    }, indent=2), encoding="utf-8")
    subprocess.run([wrangler, "deploy", "--config", str(config)], check=True)
    return True
