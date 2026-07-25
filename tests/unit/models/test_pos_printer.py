"""PosPrinter model + split-print ticket routing tests.

Pure logic: no DB — printers/lines are MagicMock-shaped stand-ins, matching
the unit conventions for POS model tests.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from models.pos_printer import PosPrinter
from utils.pos_helpers import build_print_tickets


def _printer(role="customer", conn="agent_network", cats=None, name="P1"):
    p = MagicMock(spec=PosPrinter)
    p.name = name
    p.role = role
    p.connection_type = conn
    p.category_ids = cats
    p.covers_category = lambda cid, _cats=cats: (not _cats) or cid in _cats
    p.agent_printer_payload.return_value = {"connection": "network", "host": "10.0.0.1", "port": 9100}
    return p


def _line(name, qty, total, category_id=None):
    product = SimpleNamespace(name=name, name_ar=None, category_id=category_id)
    return SimpleNamespace(
        product=product,
        product_id=1,
        quantity=Decimal(str(qty)),
        line_total=Decimal(str(total)),
    )


def _sale(lines, number="S-1", total="20.000"):
    return SimpleNamespace(sale_number=number, lines=lines, total_amount=Decimal(total))


class TestPosPrinterModel:
    def test_covers_category_empty_means_all(self):
        p = PosPrinter(category_ids=None)
        assert p.covers_category(5) is True
        assert p.covers_category(None) is True

    def test_covers_category_restricts(self):
        p = PosPrinter(category_ids=[1, 2])
        assert p.covers_category(1) is True
        assert p.covers_category(3) is False

    def test_agent_payload_network(self):
        p = PosPrinter(connection_type="agent_network", host="192.168.1.5", port=None, encoding="cp864")
        payload = p.agent_printer_payload()
        assert payload == {"connection": "network", "host": "192.168.1.5", "port": 9100, "encoding": "cp864"}

    def test_agent_payload_serial(self):
        p = PosPrinter(connection_type="agent_serial", serial_port="COM3", baud_rate=None)
        payload = p.agent_printer_payload()
        assert payload == {"connection": "serial", "port": "COM3", "baud": 9600}


class TestBuildPrintTickets:
    def test_customer_receipt_always_included(self):
        sale = _sale([_line("Tea", 2, "10.000")])
        tickets = build_print_tickets(sale, [_printer(role="customer")])
        assert len(tickets) == 1
        t = tickets[0]
        assert t["role"] == "customer"
        assert t["content"]["open_drawer"] is True
        texts = [l.get("text", "") for l in t["content"]["lines"]]
        assert any("S-1" in x for x in texts)
        assert any("2 x Tea" in x for x in texts)
        assert any("TOTAL 20" in x for x in texts)

    def test_kitchen_routing_by_category(self):
        sale = _sale(
            [
                _line("Burger", 1, "15.000", category_id=1),
                _line("Mug", 1, "5.000", category_id=2),
            ],
            total="20.000",
        )
        kitchen = _printer(role="kitchen", cats=[1], name="K1")
        tickets = build_print_tickets(sale, [kitchen])
        assert len(tickets) == 1
        texts = [l.get("text", "") for l in tickets[0]["content"]["lines"]]
        assert any("Burger" in x for x in texts)
        assert not any("Mug" in x for x in texts)

    def test_kitchen_without_matching_lines_skipped(self):
        sale = _sale([_line("Mug", 1, "5.000", category_id=2)])
        kitchen = _printer(role="kitchen", cats=[9])
        tickets = build_print_tickets(sale, [kitchen])
        assert tickets == []

    def test_empty_categories_printer_gets_all_lines(self):
        sale = _sale(
            [
                _line("Burger", 1, "15.000", category_id=1),
                _line("Mug", 1, "5.000", category_id=2),
            ]
        )
        kitchen = _printer(role="kitchen", cats=None)
        tickets = build_print_tickets(sale, [kitchen])
        assert len(tickets) == 1
        texts = [l.get("text", "") for l in tickets[0]["content"]["lines"]]
        assert any("Burger" in x for x in texts)
        assert any("Mug" in x for x in texts)

    def test_quantity_trimmed(self):
        sale = _sale([_line("Tea", "1.000", "3.000")])
        tickets = build_print_tickets(sale, [_printer(role="customer")])
        texts = [l.get("text", "") for l in tickets[0]["content"]["lines"]]
        assert any(x.startswith("1 x Tea") for x in texts)

    def test_mixed_roles(self):
        sale = _sale([_line("Burger", 1, "15.000", category_id=1)], total="15.000")
        printers = [
            _printer(role="customer", name="Front"),
            _printer(role="kitchen", cats=[1], name="Kitchen"),
            _printer(role="warehouse", cats=[2], name="Store"),
        ]
        tickets = build_print_tickets(sale, printers)
        roles = [t["role"] for t in tickets]
        assert roles == ["customer", "kitchen"]

    def test_no_printers_no_tickets(self):
        assert build_print_tickets(_sale([_line("A", 1, "1.000")]), []) == []
