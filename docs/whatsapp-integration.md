# WhatsApp integration: getting started

You're building the WhatsApp side of the stock quotation tool: receive a
WhatsApp message, get a quote from Pulse BI, send the reply back. The
quoting itself (matching an enquiry to stock, pricing, safety rules) is
done; you only need the transport around one function.

## 1. Check out only the quotation part

The repo also holds the owner dashboard and alert email, which you don't
need. A partial checkout keeps only the folders the quoting side uses:

```bash
git clone --filter=blob:none --sparse https://github.com/aamirsalam/pulse-bi
cd pulse-bi
git sparse-checkout set pulse_bi/quote pulse_bi/channels pulse_bi/sources pulse_bi/engine customers demo_data tests docs
git switch -c whatsapp
```

`pulse_bi/engine` is included because the config loader and the reply
formatting use two small pieces of it; you won't need to change it. To see
everything later: `git sparse-checkout disable`.

## 2. Run it

Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install flask pytest

python -m pulse_bi quote "steel hinge"
python -m pulse_bi whatsapp "20 pcs 1 1/2 x 1" --sender "+91 90000 00001"
python -m pulse_bi whatsapp "steel hinge" --sender "+91 99999 99999"    # not allowed: prints None
pytest tests/test_quote.py tests/test_whatsapp.py tests/test_enquiry_and_catalogue.py
```

Everything runs on made-up data for a small hardware shop (`demo_data/`),
configured in `customers/demo.toml`. No real customer data is involved.

## 3. The one function you call

```python
from pulse_bi.config import Customer
from pulse_bi.channels.whatsapp import handle_message

customer = Customer.load("demo")                 # loaded once, at startup
reply = handle_message(text, sender, customer)   # sender: the number, any format
if reply is not None:
    send_text(sender, reply)                     # yours to write
```

- It returns `None` when there should be no reply: WhatsApp is switched off
  for the customer (`[channels] whatsapp`) or the sender isn't in
  `[whatsapp] allowed_senders`. Put your own test number in that list in
  `customers/demo.toml`.
- The reply is plain text with WhatsApp formatting (`*bold*`, `_italic_`),
  at most 5 items (`[whatsapp] max_products`).
- The catalogue is cached for `[quote] cache_seconds` (300), so it's cheap
  to call per message.

Files: `pulse_bi/channels/whatsapp.py` (the function and allow-list),
`pulse_bi/channels/text.py` (the reply text), `pulse_bi/quote/service.py`
(the quote and its safety rules).

## 4. Rules to keep

- **Staff only.** Replies go only to numbers on the allow-list. A quote
  shows the base rate (cost including tax) and "possible matches" that a
  person must confirm, so it must not go straight to customers. Answering
  customers directly is the owner's decision and needs a different reply
  format; talk to Aamir first.
- **Don't change the safety rules in `pulse_bi/quote/`** (never guess a
  product, withhold prices when stock or the rate is missing, flag
  shortages). If a rule gets in the way, raise it rather than working
  around it in the channel.
- **Secrets in environment variables only**: access tokens, the app secret,
  the verify token. Never in `customers/*.toml` or the code. The repo is
  public.
- **Don't log reply text**: it contains prices. Log the sender and status.
- Tests for anything new, runnable without WhatsApp (fake the HTTP calls).

## 5. Experimenting with the WhatsApp Business Platform

Meta's Cloud API has a free test setup. Follow Meta's own "Get started"
page for the current screens and API version; in outline:

1. **App and test number.** In Meta for Developers, create an app with the
   WhatsApp product. It gives you a test business phone number, its
   *phone number ID*, and a temporary access token (short-lived; a system
   user token is the long-lived option later). Add your own WhatsApp number
   as an allowed recipient.
2. **Public HTTPS address for your laptop.** Meta must reach your webhook,
   so run the Flask app locally and expose it with a tunnel (e.g.
   `cloudflared tunnel --url http://localhost:5000` or ngrok).
3. **Webhook verification (GET).** Meta calls your URL with `hub.mode`,
   `hub.verify_token` and `hub.challenge`. If the token matches the one you
   entered in the app settings, answer `200` with the challenge as plain
   text (not JSON). Then subscribe to the **`messages`** field, or no
   messages arrive.
4. **Incoming messages (POST).** Check the `X-Hub-Signature-256` header: an
   HMAC-SHA256 of the raw request body keyed with your **app secret**, sent
   as `sha256=<hex>`; reject anything that doesn't match. Answer `200`
   quickly. Pull out the sender number and text of text messages, ignore
   status updates and other message types, and ignore repeats of a message
   ID you've already handled (Meta retries).
5. **Reply.** `POST https://graph.facebook.com/<version>/<phone number ID>/messages`
   with the access token, sending a text message to the sender. Free-form
   replies work while the person messaged you in the last 24 hours, which
   is always the case here since staff message first. Outside that window
   Meta requires approved templates.

## 6. Where your code goes

- A new module, e.g. `pulse_bi/channels/whatsapp_webhook.py`: a Flask
  blueprint with the GET verification and POST handler, and the send
  function.
- Register the blueprint in `create_app()` in `pulse_bi/web.py`, only when
  `customer.channels["whatsapp"]` is on. (`web.py` imports the dashboard
  code, so for local runs either `git sparse-checkout add pulse_bi/dashboard
  pulse_bi/templates` or start your blueprint from a small app of your own
  while experimenting.)
- Settings in `[whatsapp]` of the customer config (e.g. the phone number ID,
  the API version); secrets in environment variables such as
  `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`.
- Tests in `tests/test_whatsapp_webhook.py`: verification, a bad signature
  rejected, a text message producing one reply, a non-allowed sender
  producing none, a repeated message ID handled once.

Later, for free-text messages that don't name an item exactly ("20 sheet
venam, 8 adi x 4 adi"), `pulse_bi/quote/enquiry_parser.py` can read them
with a local AI model (Ollama, off by default); see its docstring.

Open a pull request to `main` when something works end to end; the tests
run on GitHub automatically.
