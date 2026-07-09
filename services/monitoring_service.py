from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
import logging
import psutil
import os
import re
from sqlalchemy import func, text
from extensions import db
from utils.db_safety import atomic_transaction
from models import AuditLog, Sale, User

logger = logging.getLogger(__name__)

class MonitoringService:
    _TABLE_NAME_RE = re.compile(r'^[a-z0-9_]+$')
    _TRUNCATE_BLOCKED_TABLES = frozenset({
        'users', 'roles', 'tenants', 'audit_logs', 'system_settings',
        'payment_vault', 'card_vault', 'api_keys',
    })
    _STATS_BLOCKED_TABLES = _TRUNCATE_BLOCKED_TABLES

    @staticmethod
    def _is_sensitive_stats_table(table_name: str) -> bool:
        return (table_name or '').strip().lower() in MonitoringService._STATS_BLOCKED_TABLES

    @staticmethod
    def _resolve_known_table(table_name: str) -> str | None:
        from sqlalchemy import inspect
        if not table_name:
            return None
        normalized = table_name.strip().lower()
        if not MonitoringService._TABLE_NAME_RE.match(normalized):
            return None
        table_names = {name.lower(): name for name in inspect(db.engine).get_table_names()}
        return table_names.get(normalized)

    @staticmethod
    def log_system_stats_action(visible_tables, restricted_tables):
        new_log = AuditLog(
            action='view_system_stats',
            changes={'visible_tables': visible_tables, 'restricted_tables': restricted_tables},
        )
        db.session.add(new_log)
        db.session.flush()


    @staticmethod
    def get_system_stats_context(resolve_table_fn, is_sensitive_table_fn) -> Tuple[Dict[str, int], int]:
        db_stats = {}
        restricted_count = 0

        try:
            result = db.session.execute(
                text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public'")
            )
            for row in result.fetchall():
                safe_table = resolve_table_fn(row[0])
                if not safe_table:
                    continue
                if is_sensitive_table_fn(safe_table):
                    restricted_count += 1
                    continue
                count = db.session.execute(
                    text(f'SELECT COUNT(*) FROM "{safe_table}"')
                ).scalar()
                db_stats[safe_table] = count
        except Exception:
            pass

        MonitoringService.log_system_stats_action(len(db_stats), restricted_count)

        return db_stats, restricted_count

    @staticmethod
    def get_activity_monitor_context(tid, scoped_branch_id) -> Dict[str, Any]:
        recent_audits = AuditLog.query.filter_by(tenant_id=tid).order_by(
            AuditLog.created_at.desc()
        ).limit(100).all()

        active_users = User.query.filter(
            User.last_seen >= datetime.now(timezone.utc) - timedelta(minutes=30),
            User.is_active == True,
            User.tenant_id == tid,
        ).all()

        recent_sales = Sale.query.filter(
            Sale.created_at >= datetime.now(timezone.utc) - timedelta(hours=24),
            Sale.tenant_id == tid,
        )
        if scoped_branch_id is not None:
            recent_sales = recent_sales.filter(Sale.branch_id == scoped_branch_id)
        recent_sales = recent_sales.order_by(Sale.created_at.desc()).limit(20).all()

        stats = {
            'active_now': len(active_users),
            'today_sales': len(recent_sales),
            'recent_actions': len(recent_audits)
        }

        return {
            'recent_audits': recent_audits,
            'active_users': active_users,
            'recent_sales': recent_sales,
            'stats': stats
        }

    @staticmethod
    def get_performance_metrics_data() -> Dict[str, Any]:
        basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        performance_file = os.path.join(basedir, 'logs', 'performance.log')
        slow_queries = []

        if os.path.exists(performance_file):
            with open(performance_file, 'r', encoding='utf-8') as f:
                for line in f.readlines()[-200:]:
                    if 'SLOW' in line:
                        slow_queries.append(line.strip())

        return {
            'slow_queries_count': len(slow_queries),
            'slow_queries': slow_queries[-20:]
        }

    @staticmethod
    def check_database() -> Dict:
        try:
            db.session.execute(text('SELECT 1'))
            return {'status': 'connected', 'healthy': True}
        except Exception as e:
            return {'status': 'error', 'healthy': False, 'error': str(e)}

    @staticmethod
    def get_disk_usage() -> Dict:
        try:
            disk = psutil.disk_usage('/')
            return {
                'total_gb': round(disk.total / (1024**3), 2),
                'used_gb': round(disk.used / (1024**3), 2),
                'free_gb': round(disk.free / (1024**3), 2),
                'percent': disk.percent,
                'healthy': disk.percent < 90
            }
        except Exception:
            return {'healthy': True, 'error': 'unavailable'}

    @staticmethod
    def get_memory_usage() -> Dict:
        try:
            memory = psutil.virtual_memory()
            return {
                'total_mb': round(memory.total / (1024**2), 2),
                'used_mb': round(memory.used / (1024**2), 2),
                'percent': memory.percent,
                'healthy': memory.percent < 85
            }
        except Exception:
            return {'healthy': True, 'error': 'unavailable'}

    @staticmethod
    def get_system_health() -> Dict:
        return {
            'timestamp': datetime.now().isoformat(),
            'database': MonitoringService.check_database(),
            'disk': MonitoringService.get_disk_usage(),
            'memory': MonitoringService.get_memory_usage(),
            'cpu': MonitoringService.get_cpu_usage(),
            'status': 'healthy'
        }

    @staticmethod
    def get_cpu_usage() -> Dict:
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            return {
                'percent': cpu_percent,
                'cores': psutil.cpu_count(),
                'healthy': cpu_percent < 80
            }
        except Exception:
            return {'healthy': True, 'error': 'unavailable'}

    @staticmethod
    def get_application_metrics() -> Dict:
        from models import Sale, Customer, Product

        try:
            return {
                'total_sales': Sale.query.count(),
                'total_customers': Customer.query.count(),
                'total_products': Product.query.count(),
                'active_customers': Customer.query.filter_by(is_active=True).count(),
                'low_stock_products': Product.query.filter(
                    Product.current_stock <= Product.min_stock_alert
                ).count()
            }
        except Exception as e:
            return {'error': str(e)}

    @staticmethod
    def log_performance_metric(metric_name: str, value: float, tags: Dict = None):
        try:
            basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
            logs_dir = os.path.join(basedir, 'logs')
            metrics_file = os.path.join(logs_dir, 'performance.log')

            os.makedirs(logs_dir, exist_ok=True)

            with open(metrics_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().isoformat()
                tags_str = ','.join([f'{k}={v}' for k, v in (tags or {}).items()])
                f.write(f'{timestamp}|{metric_name}={value}|{tags_str}\n')
        except Exception:
            pass
