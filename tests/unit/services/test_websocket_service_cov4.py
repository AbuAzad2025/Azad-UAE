"""Cov4: websocket_service — CORS branches + broadcast/notify no-op and emit arcs."""

from __future__ import annotations

from unittest.mock import MagicMock

import services.websocket_service as ws


class _Cfg(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def _make_app(**cfg):
    app = MagicMock()
    base = {"DEBUG": False, "APP_ENV": "production", "CORS_ORIGINS": [], "PORT": 5000}
    base.update(cfg)
    app.config = _Cfg(base)
    return app


def test_cors_origins_prod_with_origins():
    app = _make_app(APP_ENV="production", DEBUG=False, CORS_ORIGINS=[" https://a.example.com/ ", ""])
    assert ws._socketio_cors_origins(app) == ["https://a.example.com"]


def test_cors_origins_prod_empty_warns(caplog):
    app = _make_app(APP_ENV="production", DEBUG=False, CORS_ORIGINS=[])
    with caplog.at_level("WARNING"):
        assert ws._socketio_cors_origins(app) == []


def test_cors_origins_dev_localhost():
    app = _make_app(APP_ENV="development", DEBUG=True, PORT=5001)
    origins = ws._socketio_cors_origins(app)
    assert "http://localhost:5001" in origins
    assert "http://localhost:5000" in origins


def test_cors_origins_debug_true_forces_dev():
    app = _make_app(APP_ENV="production", DEBUG=True, PORT=5000)
    origins = ws._socketio_cors_origins(app)
    assert origins[0].startswith("http://localhost:")


def test_broadcast_noop_when_socketio_none(monkeypatch):
    monkeypatch.setattr(ws, "socketio", None)
    assert ws.broadcast_sale_created({"id": 1}) is None
    assert ws.broadcast_payment_received({"id": 2}) is None
    assert ws.notify_user(5, "hi") is None
    assert ws.broadcast_stock_alert({"sku": "x"}) is None


def test_broadcast_emits_when_socketio_present(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(ws, "socketio", fake)
    ws.broadcast_sale_created({"id": 1})
    fake.emit.assert_any_call("sale_created", {"id": 1})
    ws.broadcast_payment_received({"id": 2})
    fake.emit.assert_any_call("payment_received", {"id": 2})
    ws.notify_user(7, "hello", "warning")
    fake.emit.assert_any_call(
        "notification", {"message": "hello", "type": "warning"}, room="user_7"
    )
    ws.notify_user(8, "hello2")
    fake.emit.assert_any_call(
        "notification", {"message": "hello2", "type": "info"}, room="user_8"
    )
    ws.broadcast_stock_alert({"sku": "x"})
    fake.emit.assert_any_call("stock_alert", {"sku": "x"})


def test_init_socketio_registers_handlers(app, monkeypatch):
    created = {}

    class FakeSIO:
        def __init__(self, *a, **k):
            created.update(k)
            self.handlers = {}

        def on(self, event):
            def deco(fn):
                self.handlers[event] = fn
                return fn

            return deco

        def emit(self, *a, **k):
            pass

    monkeypatch.setattr(ws, "SocketIO", FakeSIO)
    monkeypatch.setattr(ws, "emit", MagicMock())
    monkeypatch.delenv("REDIS_URL", raising=False)
    sio = ws.init_socketio(app)
    assert isinstance(sio, FakeSIO)
    assert set(sio.handlers) == {"connect", "disconnect", "ping"}
    # exercise handlers with anonymous user (is_authenticated False branches)
    sio.handlers["connect"]()
    sio.handlers["disconnect"]()
    sio.handlers["ping"]()
    ws_module_socketio = ws.socketio
    assert ws_module_socketio is sio
