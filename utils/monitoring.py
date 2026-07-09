"""
Advanced Monitoring and Logging System
"""
import time
import logging
import json
from datetime import datetime, timezone
from functools import wraps
from flask import request, g, current_app
from extensions import db
from sqlalchemy import text


class PerformanceMonitor:
    """Monitor application performance"""
    
    @staticmethod
    def log_request():
        """Log request details"""
        g.start_time = time.time()
        g.request_id = request.headers.get('X-Request-Id', 'N/A')
    
    @staticmethod
    def log_response(response):
        """Log response details and timing"""
        if hasattr(g, 'start_time'):
            elapsed = time.time() - g.start_time
            
            log_data = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'request_id': getattr(g, 'request_id', 'N/A'),
                'method': request.method,
                'path': request.path,
                'status': response.status_code,
                'duration_ms': round(elapsed * 1000, 2),
                'user_agent': request.user_agent.string[:100],
                'ip': request.remote_addr
            }
            
            if elapsed > 1.0:
                current_app.logger.warning(f"SLOW REQUEST: {json.dumps(log_data)}")
            elif elapsed > 0.5:
                current_app.logger.info(f"REQUEST: {json.dumps(log_data)}")
        
        return response
    
    @staticmethod
    def monitor_endpoint(f):
        """Decorator to monitor endpoint performance"""
        @wraps(f)
        def decorated(*args, **kwargs):
            start = time.time()
            
            try:
                result = f(*args, **kwargs)
                duration = time.time() - start
                
                current_app.logger.info(
                    f"ENDPOINT {f.__name__}: {round(duration * 1000, 2)}ms"
                )
                
                return result
            except Exception as e:
                duration = time.time() - start
                current_app.logger.error(
                    f"ENDPOINT ERROR {f.__name__}: {str(e)} after {round(duration * 1000, 2)}ms"
                )
                raise
        
        return decorated


class DatabaseMonitor:
    """Monitor database performance"""
    
    @staticmethod
    def log_query(query, duration):
        """Log slow database queries"""
        if duration > 0.1:  # 100ms threshold
            current_app.logger.warning(
                f"SLOW QUERY ({round(duration * 1000, 2)}ms): {query}"
            )


class ErrorLogger:
    """Enhanced error logging"""
    
    @staticmethod
    def log_error(error, context=None):
        """Log error with context"""
        error_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'error_type': type(error).__name__,
            'error_message': str(error),
            'request_id': getattr(g, 'request_id', 'N/A'),
            'path': request.path if request else 'N/A',
            'method': request.method if request else 'N/A',
            'user': getattr(g, 'user', 'anonymous'),
            'context': context or {}
        }
        
        current_app.logger.error(
            f"ERROR: {json.dumps(error_data, indent=2)}"
        )
        
        try:
            from models.audit import AuditLog
            audit = AuditLog(
                action='error',
                details=json.dumps(error_data),
                ip_address=request.remote_addr if request else None
            )
            db.session.add(audit)
            db.session.flush()
        except Exception:
            pass


class MetricsCollector:
    """Collect application metrics"""
    
    @staticmethod
    def record_metric(metric_name, value, tags=None):
        """Record a metric"""
        metric_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'metric': metric_name,
            'value': value,
            'tags': tags or {}
        }
        
        current_app.logger.info(f"METRIC: {json.dumps(metric_data)}")
        
    
    @staticmethod
    def record_sale(amount, currency):
        """Record sale metric"""
        MetricsCollector.record_metric(
            'sale_created',
            amount,
            {'currency': currency}
        )
    
    @staticmethod
    def record_payment(amount, method):
        """Record payment metric"""
        MetricsCollector.record_metric(
            'payment_received',
            amount,
            {'method': method}
        )
    
    @staticmethod
    def record_stock_change(product_id, quantity, movement_type):
        """Record stock change metric"""
        MetricsCollector.record_metric(
            'stock_movement',
            quantity,
            {'product_id': product_id, 'type': movement_type}
        )


class HealthCheck:
    """Application health check"""
    
    @staticmethod
    def check_database():
        """Check database connectivity"""
        try:
            db.session.execute(text('SELECT 1'))
            return {'status': 'healthy', 'message': 'Database connected'}
        except Exception as e:
            return {'status': 'unhealthy', 'message': str(e)}
    
    @staticmethod
    def check_redis():
        """Check Redis connectivity"""
        try:
            from extensions import cache
            cache.set('health_check', 'ok', timeout=10)
            result = cache.get('health_check')
            if result == 'ok':
                return {'status': 'healthy', 'message': 'Redis connected'}
            return {'status': 'unhealthy', 'message': 'Redis not responding'}
        except Exception as e:
            return {'status': 'unhealthy', 'message': str(e)}
    
    @staticmethod
    def check_disk_space():
        """Check disk space"""
        try:
            import os
            import shutil
            total, used, free = shutil.disk_usage(os.path.abspath(os.sep))
            percent_used = (used / total) * 100
            
            if percent_used > 90:
                return {'status': 'unhealthy', 'message': f'Disk {percent_used:.1f}% full'}
            return {'status': 'healthy', 'message': f'Disk {percent_used:.1f}% used'}
        except Exception as e:
            return {'status': 'unknown', 'message': str(e)}
    
    @staticmethod
    def get_health_status():
        """Get overall health status"""
        checks = {
            'database': HealthCheck.check_database(),
            'redis': HealthCheck.check_redis(),
            'disk': HealthCheck.check_disk_space()
        }
        
        overall_healthy = all(
            check['status'] == 'healthy' 
            for check in checks.values()
        )
        
        return {
            'status': 'healthy' if overall_healthy else 'unhealthy',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'checks': checks
        }


def setup_advanced_logging(app):
    """Setup advanced logging configuration"""
    
    import os
    logs_dir = os.path.join(app.root_path, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    
    perf_handler = logging.FileHandler(
        os.path.join(logs_dir, 'performance.log')
    )
    perf_handler.setLevel(logging.INFO)
    perf_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    )
    perf_handler.setFormatter(perf_formatter)
    
    error_handler = logging.FileHandler(
        os.path.join(logs_dir, 'errors.log')
    )
    error_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s'
    )
    error_handler.setFormatter(error_formatter)
    
    app.logger.addHandler(perf_handler)
    app.logger.addHandler(error_handler)
    
    @app.before_request
    def before_request():
        PerformanceMonitor.log_request()
    
    @app.after_request
    def after_request(response):
        return PerformanceMonitor.log_response(response)
    
    @app.route('/health')
    def health_check():
        from flask import jsonify
        health = HealthCheck.get_health_status()
        status_code = 200 if health['status'] == 'healthy' else 503
        return jsonify(health), status_code
    
    @app.route('/metrics')
    def metrics():
        from flask import jsonify
        from flask_login import current_user
        
        if not current_user.is_authenticated or not current_user.is_owner:
            return jsonify({'error': 'Unauthorized'}), 403
        
        metrics_data = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'health': HealthCheck.get_health_status(),
            'app_info': {
                'version': app.config.get('APP_VERSION'),
                'environment': app.config.get('APP_ENV')
            }
        }
        
        return jsonify(metrics_data)

