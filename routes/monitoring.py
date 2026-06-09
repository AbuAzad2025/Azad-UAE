from flask import Blueprint, jsonify, render_template
from flask_login import login_required
from services.logging_core import LoggingCore
from utils.decorators import admin_required

monitoring_bp = Blueprint('monitoring', __name__, url_prefix='/monitoring')


@monitoring_bp.route('/health')
def health():
    health_data = LoggingCore.get_system_health()
    status_code = 200 if health_data.get('status') == 'healthy' else 503
    return jsonify(health_data), status_code


@monitoring_bp.route('/metrics')
@login_required
@admin_required
def metrics():
    app_metrics = LoggingCore.get_app_metrics()
    return jsonify(app_metrics)


@monitoring_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    health = LoggingCore.get_system_health()
    metrics = LoggingCore.get_app_metrics()

    return render_template('monitoring/dashboard.html',
                         health=health,
                         metrics=metrics)

