"""POS hardware pipeline — cross-module integration matrix.

Exercises the full seam without a database:
scale barcode → product lookup/serialize → checkout line merge →
sale → split-print tickets → agent ESC/POS bytes → terminal minor units.

External boundaries (Stripe HTTP, printer sockets) stay mocked; the JS
scale parser is checked for parity with the Python parser via node.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts.hardware_agent import pos_hardware_agent as agent
from services import pos_terminal_service as pts
from utils.pos_helpers import (
    build_print_tickets,
    merge_checkout_lines,
    parse_scale_barcode,
    serialize_pos_product,
)


def _make_scale_code(item_code: int, grams: int) -> str:
    body = f"20{str(item_code).zfill(5)}{str(grams).zfill(5)}"
    digits = [int(d) for d in body]
    checksum = (10 - (sum(digits[::2]) + 3 * sum(digits[1::2])) % 10) % 10
    return f"{body}{checksum}"


def _product(pid=1, unit="kg", name="Flour"):
    return SimpleNamespace(
        id=pid,
        name=name,
        name_ar=None,
        sku="SKU1",
        barcode=str(pid).zfill(5),
        regular_price=Decimal("5.000"),
        current_stock=Decimal("10"),
        is_active=True,
        unit=unit,
    )


def _sale(lines, number="POS-2026-0001", total="25.500"):
    sale = MagicMock()
    sale.sale_number = number
    sale.lines = lines
    sale.total_amount = Decimal(total)
    return sale


def _line(name, qty, total, category_id=None):
    return SimpleNamespace(
        product=SimpleNamespace(name=name, name_ar=None, category_id=category_id),
        product_id=1,
        quantity=Decimal(str(qty)),
        line_total=Decimal(str(total)),
    )


def _printer(role, cats=None, name="P"):
    p = MagicMock()
    p.name = name
    p.role = role
    p.connection_type = "agent_network"
    p.category_ids = cats
    p.covers_category = lambda cid, _c=cats: (not _c) or cid in _c
    p.agent_printer_payload.return_value = {"connection": "network", "host": "10.0.0.1", "port": 9100}
    return p


class TestScaleScanToCheckoutLine:
    def test_weight_flow_end_to_end(self):
        code = _make_scale_code(1, 1750)
        parsed = parse_scale_barcode(code)
        assert parsed is not None
        assert parsed["weight_kg"] == Decimal("1.750")

        product = _product(unit="kg")
        payload = serialize_pos_product(product, {})
        assert payload["is_weight_product"] is True

        merged = merge_checkout_lines(
            [{"product_id": product.id, "quantity": float(parsed["weight_kg"]), "unit_price": 5.0}]
        )
        assert merged[0]["quantity"] == pytest.approx(1.75, abs=1e-6)

    def test_piece_product_not_weight_flagged(self):
        payload = serialize_pos_product(_product(unit="pcs"), {})
        assert payload["is_weight_product"] is False


class TestSaleToAgentBytes:
    def test_full_pipeline_byte_structure(self):
        sale = _sale(
            [
                _line("Burger", 1, "15.000", category_id=1),
                _line("Mug", 1, "10.500", category_id=2),
            ]
        )
        printers = [
            _printer("customer", name="Front"),
            _printer("kitchen", cats=[1], name="Kitchen"),
        ]
        tickets = build_print_tickets(sale, printers)
        assert [t["role"] for t in tickets] == ["customer", "kitchen"]

        for ticket in tickets:
            payload = agent.build_receipt_bytes(ticket["content"])
            assert payload.startswith(b"\x1b@")
            assert payload.endswith(b"\x1dV\x00")

        customer_bytes = agent.build_receipt_bytes(tickets[0]["content"])
        assert b"\x1bp\x00\x19\xfa" in customer_bytes  # drawer kick
        assert b"TOTAL 25.5" in customer_bytes

        kitchen_bytes = agent.build_receipt_bytes(tickets[1]["content"])
        assert b"\x1bp\x00\x19\xfa" not in kitchen_bytes  # no drawer on kitchen
        assert b"Burger" in kitchen_bytes
        assert b"Mug" not in kitchen_bytes

    def test_tickets_do_not_mutate_sale(self):
        lines = [_line("Burger", 1, "15.000", category_id=1)]
        sale = _sale(lines)
        build_print_tickets(sale, [_printer("customer")])
        assert len(sale.lines) == 1


class TestTerminalConsistency:
    def test_minor_units_match_quantized_total(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")

        class _Resp:
            def read(self):
                return json.dumps({"id": "pi_1", "client_secret": "s", "status": "ok"}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = req.data.decode()
            return _Resp()

        monkeypatch.setattr(pts.urllib.request, "urlopen", fake_urlopen)
        intent = pts.create_terminal_payment_intent("25.500", currency="AED", tenant_id=3)
        assert intent["amount_minor"] == 2550
        assert "metadata%5Btenant_id%5D=3" in captured["body"]


@pytest.mark.skipif(not shutil.which("node"), reason="node runtime unavailable")
class TestScaleParserParity:
    VECTORS = [
        (1, 1),
        (1, 250),
        (12345, 1500),
        (77777, 12345),
        (99999, 99999),
    ]

    def test_js_and_python_parsers_agree(self):
        script = (
            'const { parseScaleBarcodeLocal } = require("./static/js/pos/offline-catalog.js");'
            "const codes = process.argv[1].split(',');"
            "console.log(JSON.stringify(codes.map(c => parseScaleBarcodeLocal(c))));"
        )
        codes = [_make_scale_code(i, g) for i, g in self.VECTORS]
        out = subprocess.run(
            ["node", "-e", script, ",".join(codes)],
            capture_output=True,
            text=True,
            check=True,
        )
        js_results = json.loads(out.stdout.strip().splitlines()[-1])
        for code, js in zip(codes, js_results, strict=True):
            py = parse_scale_barcode(code)
            assert py is not None, code
            assert js is not None, code
            assert js["itemCode"] == py["item_code"]
            assert Decimal(str(js["weightKg"])) == py["weight_kg"]
