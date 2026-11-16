import io
import json
from decimal import Decimal

import pytest

from pulse_bi.quote import enquiry_parser as P
from pulse_bi.quote.csv_catalogue import load_stock_report_csv
from pulse_bi.quote.service import Quoter
from pulse_bi.sources.base import Source
from pulse_bi.sources.lux import LuxSource


def test_feet_dimensions_override():
    assert P.extract_feet_dimensions("20 sheet venam, 8 adi x 4 adi, 2 mm") == (8.0, 4.0, "feet")
    assert P.extract_feet_dimensions("8 ft by 4 ft") == (8.0, 4.0, "feet")
    assert P.extract_feet_dimensions("8 x 4 mm") is None


def test_leading_quantity_override():
    assert P.extract_leading_quantity("20 sheets hylam") == (20.0, "sheets")
    assert P.extract_leading_quantity("5 pcs hinge") == (5.0, "pieces")
    assert P.extract_leading_quantity("hylam 20 sheets") is None


def test_overrides_correct_the_model():
    parsed = {"items": [{"product": "hylam sheet", "quantity": 2, "quantity_unit": None,
                         "length": None, "width": None, "dimension_unit": None}]}
    P.apply_overrides("20 sheets hylam 8 adi x 4 adi", parsed)
    item = parsed["items"][0]
    assert (item["quantity"], item["quantity_unit"], item["length"], item["width"]) == (20.0, "sheets", 8.0, 4.0)


def test_overrides_refuse_bad_quantities():
    with pytest.raises(ValueError):
        P.apply_overrides("hinge", {"items": [{"product": "hinge", "quantity": 0}]})
    with pytest.raises(ValueError):
        P.apply_overrides("hinge", {"products": []})


def test_parse_enquiry_calls_the_model(monkeypatch):
    # Not a test of the model itself (Ollama isn't run here), only of the call around it.
    sent = {}
    content = {"items": [{"product": "steel hinge", "quantity": 4, "quantity_unit": "pieces"}]}

    def fake_urlopen(request, timeout):
        sent.update(json.loads(request.data))
        return io.BytesIO(json.dumps({"message": {"content": json.dumps(content)}}).encode())

    monkeypatch.setattr(P.urllib.request, "urlopen", fake_urlopen)
    parsed = P.parse_enquiry("hinge 4 ennam venam", model="test-model")
    assert sent["model"] == "test-model" and parsed["items"][0]["product"] == "steel hinge"


def test_request_flow_uses_the_model_only_when_needed(monkeypatch):
    class FakeSource(Source):
        def load_catalogue(self, data=None):
            return [{"name": "Steel hinge 4 in", "ref": "1", "stock": Decimal(2), "rate": Decimal(50)}]

    quoter = Quoter(FakeSource({}))
    assert P.request_flow("Steel hinge 4 in", quoter, {"enabled": True})[0]["status"] == "exact"
    assert P.request_flow("hinge onnu venam", quoter, {"enabled": False})[0]["status"] == "no_match"

    monkeypatch.setattr(P, "parse_enquiry", lambda *a, **k: {"items": [{"product": "steel hinge", "quantity": 5}]})
    result = P.request_flow("5 hinge venam", quoter, {"enabled": True})[0]
    assert result["status"] == "review" and result["products"][0]["shortage_by"] == Decimal(3)


CSV = """SourceRow,ItemName,Op.Stock,Purchase,Sales,SalesRtn,Prch.Rtn,Production,Consumption,Closing,P/Rate+Tax,P/Rate,StkValue
7,Aluminium angle 1 x 1,0,0,0,0,0,0,0,12,"1,180.50",1000,0
8,Steel hinge 4 in,0,0,0,0,0,0,0,,45,38,0
9,PVC sheet 8 x 4,0,0,0,0,0,0,0,-2,1800,1500,0
"""


def test_stock_report_csv_catalogue(tmp_path):
    path = tmp_path / "inventory_import.csv"
    path.write_text(CSV, encoding="utf-8")
    angle, hinge, sheet = load_stock_report_csv(path)
    assert (angle["rate"], angle["stock"], angle["ref"]) == (Decimal("1180.50"), Decimal(12), "row 7")
    assert hinge["stock"] is None
    assert sheet["stock"] == Decimal(-2)

    source = LuxSource({"catalogue_csv": str(path)})
    quoter = Quoter(source)
    product = quoter.quote("Aluminium angle 1 x 1")["products"][0]
    assert [p["value"] for p in product["prices"]] == [Decimal("1180.50"), Decimal("1322.16"), Decimal("1357.58")]
    assert quoter.quote("Steel hinge 4 in")["products"][0]["prices"] == []   # stock unknown
    assert quoter.quote("PVC sheet 8 x 4")["products"][0]["prices"] == []    # negative stock


def test_default_catalogue_withholds_prices(demo_data):
    class Plain(Source):
        def load(self):
            return demo_data
    assert all(entry["rate"] is None for entry in Plain({}).load_catalogue())


def test_demo_catalogue_prices_from_cost_including_tax(demo_data):
    from pulse_bi.sources.demo import DemoSource
    entry = next(e for e in DemoSource({"path": "demo_data", "tax_percent": 18}).load_catalogue(demo_data) if e["ref"] == "H300")
    cost = next(i["unit_cost"] for i in demo_data["items"] if i["code"] == "H300")
    assert float(entry["rate"]) == pytest.approx(cost * 1.18, abs=0.0001)
