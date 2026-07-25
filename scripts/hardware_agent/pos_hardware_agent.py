#!/usr/bin/env python3
"""POS hardware agent — localhost bridge to thermal printers and cash drawers.

Runs on the cashier machine (127.0.0.1:8567, loopback only). The Azad-UAE
server forwards print/drawer requests here; the agent translates them into
ESC/POS byte streams and delivers them to the printer over TCP (port 9100)
or, when pyserial is installed, a serial port.

Endpoints:
  GET  /status         → agent + printer configuration status
  POST /print-receipt  → build ESC/POS receipt from JSON content and print
  POST /open-drawer    → ESC/POS drawer-kick pulse

Request bodies are JSON::

    {
      "printer":  {"connection": "network", "host": "192.168.1.50",
                   "port": 9100, "encoding": "cp864"},
      "content":  {"lines": [{"text": "...", "align": "center",
                              "bold": true, "double": false}],
                   "cut": true, "open_drawer": false}
    }

An optional JSON config (POS_HARDWARE_AGENT_CONFIG, default
``agent_config.json`` beside this script) supplies ``default_printer`` when
the request omits it. Stdlib only; pyserial is optional.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

logger = logging.getLogger("pos_hardware_agent")

AGENT_HOST = "127.0.0.1"
AGENT_PORT = int(os.getenv("POS_HARDWARE_AGENT_PORT", "8567"))
_DEFAULT_CONFIG_PATH = Path(__file__).with_name("agent_config.json")
_CONNECT_TIMEOUT_SECONDS = 5

# ESC/POS command bytes
_ESC = b"\x1b"
_GS = b"\x1d"
CMD_INIT = _ESC + b"@"
CMD_CUT_FULL = _GS + b"V\x00"
CMD_DRAWER_PIN2 = _ESC + b"p\x00\x19\xfa"
_ALIGN = {"left": b"\x1ba\x00", "center": b"\x1ba\x01", "right": b"\x1ba\x02"}
_BOLD_ON = _ESC + b"E\x01"
_BOLD_OFF = _ESC + b"E\x00"
_DOUBLE_ON = _GS + b"!\x11"
_DOUBLE_OFF = _GS + b"!\x00"


class AgentError(Exception):
    """User-safe agent failure surfaced in the JSON response."""


def _load_config() -> dict:
    path = Path(os.getenv("POS_HARDWARE_AGENT_CONFIG", str(_DEFAULT_CONFIG_PATH)))
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Ignoring unreadable agent config %s: %s", path, exc)
        return {}


def resolve_printer(body: dict) -> dict:
    """Printer definition from the request, falling back to agent config."""
    printer = body.get("printer") or _load_config().get("default_printer") or {}
    if not printer:
        raise AgentError("لا توجد طابعة مهيأة (لا في الطلب ولا في إعداد الوكيل).")
    connection = printer.get("connection", "network")
    if connection == "network" and not printer.get("host"):
        raise AgentError("طابعة الشبكة تحتاج عنوان host.")
    if connection == "serial" and not printer.get("port"):
        raise AgentError("الطابعة التسلسلية تحتاج اسم port.")
    return printer


def _encode(text: str, encoding: str) -> bytes:
    try:
        return str(text).encode(encoding, errors="replace")
    except LookupError:
        return str(text).encode("utf-8", errors="replace")


def escpos_line(
    text: str, *, align: str = "left", bold: bool = False, double: bool = False, encoding: str = "cp864"
) -> bytes:
    """One formatted text line as ESC/POS bytes."""
    out = bytearray()
    out += _ALIGN.get(align, _ALIGN["left"])
    out += _BOLD_ON if bold else _BOLD_OFF
    out += _DOUBLE_ON if double else _DOUBLE_OFF
    out += _encode(text, encoding) + b"\n"
    out += _BOLD_OFF + _DOUBLE_OFF + _ALIGN["left"]
    return bytes(out)


def build_receipt_bytes(content: dict, *, encoding: str = "cp864") -> bytes:
    """Full receipt payload: init, lines, optional drawer pulse, cut."""
    out = bytearray(CMD_INIT)
    for line in content.get("lines") or []:
        if isinstance(line, str):
            line = {"text": line}
        if line.get("separator"):
            text = "-" * int(line.get("width") or 32)
            out += escpos_line(text, encoding=encoding)
            continue
        out += escpos_line(
            line.get("text", ""),
            align=line.get("align", "left"),
            bold=bool(line.get("bold")),
            double=bool(line.get("double")),
            encoding=encoding,
        )
    if content.get("feed"):
        out += b"\n" * min(int(content["feed"]), 10)
    if content.get("open_drawer"):
        out += CMD_DRAWER_PIN2
    if content.get("cut", True):
        out += b"\n\n" + CMD_CUT_FULL
    return bytes(out)


def send_network(payload: bytes, host: str, port: int = 9100) -> None:
    try:
        with socket.create_connection((host, int(port)), timeout=_CONNECT_TIMEOUT_SECONDS) as sock:
            sock.sendall(payload)
    except OSError as exc:
        raise AgentError(f"تعذر الوصول إلى الطابعة {host}:{port}.") from exc


def send_serial(payload: bytes, port: str, baud: int = 9600) -> None:
    try:
        import serial  # pyserial — optional dependency
    except ImportError as exc:
        raise AgentError("الطباعة التسلسلية تحتاج تثبيت pyserial على جهاز الكاشير.") from exc
    try:
        with serial.Serial(port, int(baud), timeout=_CONNECT_TIMEOUT_SECONDS) as ser:
            ser.write(payload)
    except Exception as exc:
        raise AgentError(f"تعذر الوصول إلى المنفذ التسلسلي {port}.") from exc


def deliver(payload: bytes, printer: dict) -> str:
    """Route bytes to the configured connection; returns the channel used."""
    connection = printer.get("connection", "network")
    if connection == "serial":
        send_serial(payload, printer["port"], printer.get("baud", 9600))
        return "serial"
    send_network(payload, printer["host"], printer.get("port", 9100))
    return "network"


class AgentHandler(BaseHTTPRequestHandler):
    server_version = "PosHardwareAgent/1.0"

    def log_message(self, fmt, *args):  # quiet default stderr chatter
        logger.debug(fmt, *args)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 256 * 1024:
            raise AgentError("حمولة الطلب غير صالحة.")
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AgentError("جسم الطلب ليس JSON صالحاً.") from exc

    def do_GET(self):
        if self.path != "/status":
            self._send_json(404, {"error": "not found"})
            return
        config = _load_config()
        printer = config.get("default_printer") or {}
        self._send_json(
            200,
            {
                "status": "connected",
                "agent": self.server_version,
                "printer_configured": bool(printer),
                "printer_connection": printer.get("connection"),
                "serial_available": _serial_available(),
            },
        )

    def do_POST(self):
        try:
            body = self._read_json()
            if self.path == "/print-receipt":
                self._handle_print(body)
            elif self.path == "/open-drawer":
                self._handle_drawer(body)
            else:
                self._send_json(404, {"error": "not found"})
        except AgentError as exc:
            self._send_json(422, {"success": False, "error": str(exc)})
        except Exception:  # noqa: BLE001 — agent must never wedge the register
            logger.exception("Unhandled agent failure on %s", self.path)
            self._send_json(500, {"success": False, "error": "خطأ داخلي في وكيل الأجهزة."})

    def _handle_print(self, body: dict) -> None:
        printer = resolve_printer(body)
        content = body.get("content") or {}
        encoding = printer.get("encoding", "cp864")
        payload = build_receipt_bytes(content, encoding=encoding)
        channel = deliver(payload, printer)
        self._send_json(200, {"success": True, "channel": channel, "bytes": len(payload)})

    def _handle_drawer(self, body: dict) -> None:
        printer = resolve_printer(body)
        channel = deliver(CMD_DRAWER_PIN2, printer)
        self._send_json(200, {"success": True, "channel": channel})


def _serial_available() -> bool:
    try:
        import serial  # noqa: F401
    except ImportError:
        return False
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer((AGENT_HOST, AGENT_PORT), AgentHandler)
    logger.info("POS hardware agent listening on http://%s:%d", AGENT_HOST, AGENT_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
