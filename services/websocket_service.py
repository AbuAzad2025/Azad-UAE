from flask import Flask
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import current_user
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

socketio = None


def _socketio_cors_origins(app: Flask):
    """Production: CORS_ORIGINS from config only. Dev: localhost / 127.0.0.1."""
    debug = bool(app.config.get('DEBUG'))
    app_env = (app.config.get('APP_ENV') or 'production').strip().lower()
    is_prod = not debug and app_env == 'production'

    if is_prod:
        origins = [
            origin.strip().rstrip('/')
            for origin in (app.config.get('CORS_ORIGINS') or [])
            if origin and origin.strip()
        ]
        if not origins:
            logger.warning('[WebSocket] CORS_ORIGINS empty in production; cross-origin Socket.IO disabled')
        return origins

    port = int(app.config.get('PORT', 5000))
    return [
        f'http://localhost:{port}',
        f'http://127.0.0.1:{port}',
        'http://localhost:5000',
        'http://127.0.0.1:5000',
    ]


def init_socketio(app: Flask):
    global socketio

    cors_origins = _socketio_cors_origins(app)
    socketio = SocketIO(
        app,
        cors_allowed_origins=cors_origins,
        async_mode='threading',
        logger=False,
        engineio_logger=False
    )
    
    @socketio.on('connect')
    def handle_connect():
        if current_user.is_authenticated:
            join_room(f'user_{current_user.id}')
            emit('connected', {'status': 'connected'})
            logger.info(f"User {current_user.id} connected via WebSocket")
    
    @socketio.on('disconnect')
    def handle_disconnect():
        if current_user.is_authenticated:
            leave_room(f'user_{current_user.id}')
            logger.info(f"User {current_user.id} disconnected")
    
    @socketio.on('ping')
    def handle_ping(data=None):
        emit('pong', {'timestamp': datetime.now().isoformat()})
    
    logger.info("[OK] WebSocket initialized")
    return socketio


def broadcast_sale_created(sale_data):
    if socketio:
        socketio.emit('sale_created', sale_data)


def broadcast_payment_received(payment_data):
    if socketio:
        socketio.emit('payment_received', payment_data)


def notify_user(user_id, message, notification_type='info'):
    if socketio:
        socketio.emit('notification', {
            'message': message,
            'type': notification_type
        }, room=f'user_{user_id}')


def broadcast_stock_alert(product_data):
    if socketio:
        socketio.emit('stock_alert', product_data)

