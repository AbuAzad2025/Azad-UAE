"""POS hardware agent tests — ESC/POS byte building and request handling.

Pure unit tests: network delivery is mocked at the socket boundary; the
HTTP handler is exercised through direct method calls with a stubbed
request stream.
"""

from __future__ import annotations

import io
import json

import pytest

from scripts.hardware_agent import pos_hardware_agent as agent


class TestEscposBuilder:
    def test_line_alignment_and_reset(self):
        out = agent.escpos_line("Hello", align="center", bold=True)
        assert out.startswith(b"\x1ba\x01")
        assert b"\x1bE\x01" in out
        assert b"Hello\n" in out
        assert out.endswith(b"\x1bE\x00\x1d!\x00\x1ba\x00")

    def test_unknown_align_defaults_left(self):
        out = agent.escpos_line("X", align="diagonal")
        assert out.startswith(b"\x1ba\x00")

    def test_receipt_full_structure(self):
        payload = agent.build_receipt_bytes(
            {
                "lines": [
                    {"text": "Store", "align": "center", "double": True},
                    {"separator": True},
                    {"text": "Total 10.00", "bold": True},
                ],
                "cut": True,
                "open_drawer": True,
            }
        )
        assert payload.startswith(b"\x1b@")
        assert b"\x1bp\x00\x19\xfa" in payload  # drawer pulse before cut
        assert payload.endswith(b"\x1dV\x00")  # full cut last
        assert b"-" * 32 in payload

    def test_receipt_no_cut(self):
        payload = agent.build_receipt_bytes({"lines": [{"text": "A"}], "cut": False})
        assert b"\x1dV\x00" not in payload

    def test_string_line_shorthand(self):
        payload = agent.build_receipt_bytes({"lines": ["plain"]})
        assert b"plain\n" in payload

    def test_unknown_encoding_falls_back_utf8(self):
        payload = agent.escpos_line("نص", encoding="cp999")
        assert "نص".encode() in payload


class TestResolvePrinter:
    def test_request_printer_wins(self):
        p = agent.resolve_printer({"printer": {"connection": "network", "host": "10.0.0.5"}})
        assert p["host"] == "10.0.0.5"

    def test_missing_printer_raises(self, monkeypatch):
        monkeypatch.setattr(agent, "_load_config", lambda: {})
        with pytest.raises(agent.AgentError):
            agent.resolve_printer({})

    def test_network_requires_host(self):
        with pytest.raises(agent.AgentError):
            agent.resolve_printer({"printer": {"connection": "network"}})

    def test_config_default_printer(self, monkeypatch):
        monkeypatch.setattr(
            agent,
            "_load_config",
            lambda: {"default_printer": {"connection": "network", "host": "192.168.1.9"}},
        )
        p = agent.resolve_printer({})
        assert p["host"] == "192.168.1.9"


class TestDelivery:
    def test_network_delivery_sends_bytes(self, monkeypatch):
        sent = {}

        class _Sock:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def sendall(self, data):
                sent["data"] = data

        monkeypatch.setattr(agent.socket, "create_connection", lambda addr, timeout=None: _Sock())
        agent.send_network(b"abc", "10.0.0.1", 9100)
        assert sent["data"] == b"abc"

    def test_network_failure_raises_agent_error(self, monkeypatch):
        def boom(addr, timeout=None):
            raise OSError("unreachable")

        monkeypatch.setattr(agent.socket, "create_connection", boom)
        with pytest.raises(agent.AgentError):
            agent.send_network(b"abc", "10.0.0.1")

    def test_serial_without_pyserial(self, monkeypatch):
        monkeypatch.setitem(__import__("sys").modules, "serial", None)
        with pytest.raises(agent.AgentError):
            agent.send_serial(b"abc", "COM3")


class _StubHandler:
    """Minimal stub to exercise AgentHandler methods without a socket."""

    def __init__(self, body: dict):
        raw = json.dumps(body).encode("utf-8")
        self.rfile = io.BytesIO(raw)
        self.headers = {"Content-Length": str(len(raw))}
        self.wfile = io.BytesIO()
        self.responses: list[tuple[int, dict]] = []
        self.path = "/print-receipt"

    def _send_json(self, status: int, payload: dict) -> None:
        self.responses.append((status, payload))

    def log_message(self, *_args):
        pass


class TestHttpHandling:
    def test_print_receipt_success(self, monkeypatch):
        delivered = {}
        monkeypatch.setattr(
            agent, "deliver", lambda payload, printer: delivered.update({"n": len(payload)}) or "network"
        )
        handler = _StubHandler(
            {
                "printer": {"connection": "network", "host": "10.0.0.1"},
                "content": {"lines": [{"text": "Hi"}]},
            }
        )
        agent.AgentHandler._handle_print(handler, json.loads(handler.rfile.getvalue().decode()))
        status, payload = handler.responses[-1]
        assert status == 200
        assert payload["success"] is True
        assert payload["channel"] == "network"
        assert delivered["n"] > 0

    def test_open_drawer_success(self, monkeypatch):
        monkeypatch.setattr(agent, "deliver", lambda payload, printer: "network")
        handler = _StubHandler({"printer": {"connection": "network", "host": "10.0.0.1"}})
        agent.AgentHandler._handle_drawer(handler, json.loads(handler.rfile.getvalue().decode()))
        status, payload = handler.responses[-1]
        assert status == 200
        assert payload["success"] is True

    def test_unconfigured_printer_raises(self, monkeypatch):
        monkeypatch.setattr(agent, "_load_config", lambda: {})
        handler = _StubHandler({"content": {"lines": []}})
        with pytest.raises(agent.AgentError):
            agent.AgentHandler._handle_print(handler, json.loads(handler.rfile.getvalue().decode()))
