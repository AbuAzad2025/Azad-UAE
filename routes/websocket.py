from flask import Blueprint
from services.websocket_service import init_socketio

websocket_bp = Blueprint("websocket", __name__)


def register_websocket_events(app):
    socketio = init_socketio(app)

    @socketio.on("subscribe_notifications")
    def handle_subscribe(data):
        from flask_socketio import join_room
        from flask_login import current_user

        if current_user.is_authenticated:
            room = f"user_{current_user.id}"
            join_room(room)
            socketio.emit("subscribed", {"room": room}, room=room)

    return socketio
