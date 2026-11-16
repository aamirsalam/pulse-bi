"""Pulse BI: stock quotes and business insights over any accounting system.

    pulse_bi.model      the data contract every source fills
    pulse_bi.sources    one adapter per accounting system (Lux, demo, Tally...)
    pulse_bi.engine     insights from the contract (pure Python)
    pulse_bi.quote      match an enquiry to stock and price it (channel-free)
    pulse_bi.channels   web page and WhatsApp front ends over pulse_bi.quote
    pulse_bi.dashboard  owner dashboard (live page or published static site)
    pulse_bi.alerts     daily staff alert email
    pulse_bi.config     per-customer settings (customers/<name>.toml)
"""
