"""WebSocket routes — subscribe handler, auth gate, room join."""
from __future__ import annotations

from unittest.mock import MagicMock


class TestRegisterWebsocketEvents:
    """register_websocket_events — notification channel subscription."""

    def test_subscribe_joins_authenticated_user_room(self, app, mocker):
        handlers = {}

        def fake_init(_app_obj):
            inst = MagicMock()

            def on(event):
                def decorator(fn):
                    handlers[event] = fn
                    return fn
                return decorator

            inst.on = on
            inst.emit = MagicMock()
            return inst

        mocker.patch('routes.websocket.init_socketio', side_effect=fake_init)
        mock_join = mocker.patch('flask_socketio.join_room')
        user = MagicMock(is_authenticated=True, id=42)
        mocker.patch('flask_login.current_user', user)

        from routes.websocket import register_websocket_events

        socketio = register_websocket_events(app)
        handlers['subscribe_notifications']({})
        mock_join.assert_called_once_with('user_42')
        socketio.emit.assert_called_once()

    def test_subscribe_skips_unauthenticated(self, app, mocker):
        handlers = {}

        def fake_init(_app_obj):
            inst = MagicMock()

            def on(event):
                def decorator(fn):
                    handlers[event] = fn
                    return fn
                return decorator

            inst.on = on
            inst.emit = MagicMock()
            return inst

        mocker.patch('routes.websocket.init_socketio', side_effect=fake_init)
        mock_join = mocker.patch('flask_socketio.join_room')
        mocker.patch('flask_login.current_user', MagicMock(is_authenticated=False))

        from routes.websocket import register_websocket_events

        register_websocket_events(app)
        handlers['subscribe_notifications']({})
        mock_join.assert_not_called()

    def test_returns_socketio_instance(self, app, mocker):
        inst = MagicMock()
        inst.on = lambda e: (lambda fn: fn)
        mocker.patch('routes.websocket.init_socketio', return_value=inst)

        from routes.websocket import register_websocket_events

        assert register_websocket_events(app) is inst
