from flask import Flask
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import current_user
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

socketio = None


def init_socketio(app: Flask):
    global socketio
    
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
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

