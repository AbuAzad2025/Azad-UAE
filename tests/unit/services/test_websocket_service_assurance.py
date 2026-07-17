"""WebSocket service — CORS, init, broadcast registry, room routing."""

from __future__ import annotations

from unittest.mock import MagicMock


class TestCorsOrigins:
    """_socketio_cors_origins — production vs dev."""

    def test_production_uses_cors_origins_config(self, app):
        original = {k: app.config.get(k) for k in ("DEBUG", "APP_ENV", "CORS_ORIGINS")}
        try:
            app.config["DEBUG"] = False
            app.config["APP_ENV"] = "production"
            app.config["CORS_ORIGINS"] = ["https://app.example.com/"]
            from services.websocket_service import _socketio_cors_origins

            origins = _socketio_cors_origins(app)
            assert origins == ["https://app.example.com"]
        finally:
            app.config.update(original)

    def test_dev_includes_localhost(self, app):
        app.config["DEBUG"] = True
        app.config["PORT"] = 8080
        from services.websocket_service import _socketio_cors_origins

        origins = _socketio_cors_origins(app)
        assert "http://localhost:8080" in origins


class TestBroadcasts:
    """Broadcast helpers — no-op without socketio, emit when initialized."""

    def test_broadcast_sale_noop_when_socketio_none(self, mocker):
        import services.websocket_service as ws

        mocker.patch.object(ws, "socketio", None)
        ws.broadcast_sale_created({"id": 1})

    def test_broadcast_sale_emits_when_ready(self, mocker):
        import services.websocket_service as ws

        mock_io = MagicMock()
        mocker.patch.object(ws, "socketio", mock_io)
        ws.broadcast_sale_created({"id": 2})
        mock_io.emit.assert_called_once_with("sale_created", {"id": 2})

    def test_notify_user_targets_room(self, mocker):
        import services.websocket_service as ws

        mock_io = MagicMock()
        mocker.patch.object(ws, "socketio", mock_io)
        ws.notify_user(7, "hello", notification_type="alert")
        mock_io.emit.assert_called_once()
        assert mock_io.emit.call_args[1]["room"] == "user_7"

    def test_broadcast_stock_alert(self, mocker):
        import services.websocket_service as ws

        mock_io = MagicMock()
        mocker.patch.object(ws, "socketio", mock_io)
        ws.broadcast_stock_alert({"sku": "X"})
        mock_io.emit.assert_called_with("stock_alert", {"sku": "X"})

    def test_broadcast_payment_received(self, mocker):
        import services.websocket_service as ws

        mock_io = MagicMock()
        mocker.patch.object(ws, "socketio", mock_io)
        ws.broadcast_payment_received({"id": 3})
        mock_io.emit.assert_called_once_with("payment_received", {"id": 3})

    def test_production_empty_cors_logs_warning(self, app, mocker):
        original = {k: app.config.get(k) for k in ("DEBUG", "APP_ENV", "CORS_ORIGINS")}
        try:
            app.config["DEBUG"] = False
            app.config["APP_ENV"] = "production"
            app.config["CORS_ORIGINS"] = []
            mock_log = mocker.patch("services.websocket_service.logger.warning")
            from services.websocket_service import _socketio_cors_origins

            assert _socketio_cors_origins(app) == []
            mock_log.assert_called_once()
        finally:
            app.config.update(original)


class TestInitSocketio:
    """init_socketio — registers handlers and returns instance."""

    def test_init_socketio_registers_connect_handlers(self, app, mocker):
        handlers = {}

        def fake_socketio(*args, **kwargs):
            inst = MagicMock()

            def on(event):
                def decorator(fn):
                    handlers[event] = fn
                    return fn

                return decorator

            inst.on = on
            return inst

        mocker.patch("services.websocket_service.SocketIO", side_effect=fake_socketio)
        from services import websocket_service as ws

        ws.socketio = None
        io = ws.init_socketio(app)
        assert io is not None
        assert "connect" in handlers
        assert "disconnect" in handlers
        assert "ping" in handlers

    def test_connect_handler_authenticated(self, app, mocker):
        handlers = {}

        def fake_socketio(*args, **kwargs):
            inst = MagicMock()

            def on(event):
                def decorator(fn):
                    handlers[event] = fn
                    return fn

                return decorator

            inst.on = on
            return inst

        user = MagicMock(is_authenticated=True, id=9)
        mocker.patch("services.websocket_service.SocketIO", side_effect=fake_socketio)
        mocker.patch("services.websocket_service.current_user", user)
        mocker.patch("services.websocket_service.join_room")
        mocker.patch("services.websocket_service.leave_room")
        mocker.patch("services.websocket_service.emit")
        from services import websocket_service as ws

        ws.socketio = None
        ws.init_socketio(app)
        handlers["connect"]()
        handlers["ping"](None)
        handlers["disconnect"]()
