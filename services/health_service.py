"""
Health Check Service - خدمة فحص صحة النظام
مراقبة صحة النظام والخدمات المختلفة
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import logging
import os

import psutil
from flask import current_app
from sqlalchemy import func

from extensions import db
from models import PaymentVault

logger = logging.getLogger(__name__)


class HealthCheckService:
    """خدمة فحص صحة النظام"""

    @staticmethod
    def check_database():
        """فحص الاتصال بقاعدة البيانات"""
        try:
            db.session.execute(db.text("SELECT 1"))
            return {"status": "healthy", "message": "Database connection OK"}
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            return {"status": "unhealthy", "message": f"Database error: {str(e)}"}

    @staticmethod
    def check_nowpayments():
        """فحص تكوين NOWPayments"""
        try:
            vault = PaymentVault.get_platform_vault()
            if not vault:
                return {"status": "warning", "message": "Payment vault not initialized"}

            if vault.nowpayments_api_key and vault.bitcoin_address:
                return {"status": "healthy", "message": "NOWPayments configured"}
            else:
                return {
                    "status": "warning",
                    "message": "NOWPayments not fully configured",
                }
        except Exception as e:
            logger.error(f"NOWPayments health check failed: {str(e)}")
            return {"status": "unhealthy", "message": f"Error: {str(e)}"}

    @staticmethod
    def check_encryption():
        """فحص نظام التشفير"""
        try:
            # التحقق من إمكانية التشفير
            from werkzeug.security import generate_password_hash

            test_hash = generate_password_hash("test")

            if test_hash:
                return {"status": "healthy", "message": "Encryption system OK"}
            else:
                return {"status": "unhealthy", "message": "Encryption test failed"}
        except Exception as e:
            logger.error(f"Encryption health check failed: {str(e)}")
            return {"status": "unhealthy", "message": f"Error: {str(e)}"}

    @staticmethod
    def check_system_resources():
        """فحص موارد النظام"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            status = "healthy"
            warnings = []

            if cpu_percent > 90:
                status = "warning"
                warnings.append(f"High CPU usage: {cpu_percent}%")

            if memory.percent > 90:
                status = "warning"
                warnings.append(f"High memory usage: {memory.percent}%")

            if disk.percent > 90:
                status = "warning"
                warnings.append(f"Low disk space: {disk.percent}% used")

            return {
                "status": status,
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "disk_percent": disk.percent,
                "warnings": warnings if warnings else None,
            }
        except Exception as e:
            logger.error(f"System resources check failed: {str(e)}")
            return {"status": "unknown", "message": f"Error: {str(e)}"}

    @staticmethod
    def get_system_metrics():
        """الحصول على مقاييس النظام"""
        try:
            from models import Donation, PackagePurchase, CardPayment

            # إحصائيات قاعدة البيانات
            total_donations = Donation.query.count()
            total_purchases = PackagePurchase.query.count()
            total_cards = CardPayment.query.count()

            # معلومات النظام
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()

            return {
                "database": {
                    "total_donations": total_donations,
                    "total_purchases": total_purchases,
                    "total_cards": total_cards,
                },
                "process": {
                    "memory_mb": round(memory_info.rss / 1024 / 1024, 2),
                    "cpu_percent": process.cpu_percent(interval=0.1),
                    "threads": process.num_threads(),
                    "uptime_seconds": int(
                        (
                            datetime.now()
                            - datetime.fromtimestamp(process.create_time())
                        ).total_seconds()
                    ),
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to get system metrics: {str(e)}")
            return {"error": str(e)}

    @staticmethod
    def run_full_health_check():
        """تشغيل فحص صحة شامل"""
        checks = {
            "database": HealthCheckService.check_database(),
            "nowpayments": HealthCheckService.check_nowpayments(),
            "encryption": HealthCheckService.check_encryption(),
            "system": HealthCheckService.check_system_resources(),
        }

        # تحديد الحالة العامة
        statuses = [check["status"] for check in checks.values()]

        if "unhealthy" in statuses:
            overall_status = "unhealthy"
        elif "warning" in statuses:
            overall_status = "warning"
        else:
            overall_status = "healthy"

        return {
            "overall_status": overall_status,
            "checks": checks,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def get_health_data():
        """Consolidated system health data from routes/owner.py"""
        import platform

        resources = HealthCheckService.check_system_resources()

        try:
            size_result = db.session.execute(
                db.text("SELECT pg_database_size(current_database())")
            )
            db_size_bytes = size_result.scalar() or 0
            db_size_mb = db_size_bytes / (1024 * 1024)
        except Exception:
            current_app.logger.debug("Could not query pg_database_size")
            db_size_mb = 0

        health_data: dict[str, Any] = {
            "cpu": {
                "percent": resources.get("cpu_percent", 0),
                "status": (
                    "جيد"
                    if resources.get("cpu_percent", 0) < 70
                    else "تحذير"
                    if resources.get("cpu_percent", 0) < 90
                    else "خطر"
                ),
            },
            "memory": {
                "total": psutil.virtual_memory().total / (1024**3),
                "used": psutil.virtual_memory().used / (1024**3),
                "percent": resources.get("memory_percent", 0),
                "status": (
                    "جيد"
                    if resources.get("memory_percent", 0) < 70
                    else "تحذير"
                    if resources.get("memory_percent", 0) < 90
                    else "خطر"
                ),
            },
            "disk": {
                "total": psutil.disk_usage(".").total / (1024**3),
                "used": psutil.disk_usage(".").used / (1024**3),
                "free": psutil.disk_usage(".").free / (1024**3),
                "percent": resources.get("disk_percent", 0),
                "status": (
                    "جيد"
                    if resources.get("disk_percent", 0) < 70
                    else "تحذير"
                    if resources.get("disk_percent", 0) < 90
                    else "خطر"
                ),
            },
            "database": {
                "size_mb": round(db_size_mb, 2),
                "status": (
                    "جيد"
                    if db_size_mb < 500
                    else "تحذير"
                    if db_size_mb < 1000
                    else "خطر"
                ),
            },
            "system": {
                "os": platform.system(),
                "version": platform.version(),
                "python": platform.python_version(),
            },
        }

        try:
            from models import User

            active_users = (
                db.session.query(func.count(User.id))
                .filter(
                    User.last_seen
                    >= datetime.now(timezone.utc) - timedelta(minutes=30),
                    User.is_active == True,
                )
                .scalar()
                or 0
            )
        except Exception:
            current_app.logger.debug("Could not query active users")
            active_users = 0

        health_data["active_users"] = active_users
        return health_data
