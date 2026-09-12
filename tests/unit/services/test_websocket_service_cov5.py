"""Cov5: websocket_service — REDIS_URL message-queue branch."""

from __future__ import annotations

import services.websocket_service as ws


def test_init_socketio_with_redis_queue(monkeypatch, app):
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
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    sio = ws.init_socketio(app)
    assert isinstance(sio, FakeSIO)
    assert created.get("message_queue") == "redis://localhost:6379/0"
    assert set(sio.handlers) == {"connect", "disconnect", "ping"}
