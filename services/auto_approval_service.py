"""
Auto Approval Service
خدمة القبول التلقائي للتبرعات والمشتريات بعد ساعة
"""

import logging
import time
import weakref
from datetime import UTC, datetime, timedelta

from flask_babel import gettext

from extensions import db
from models import Donation, PackagePurchase
from services.logging_core import LoggingCore
from utils.db_safety import atomic_transaction

logger = logging.getLogger(__name__)


class AutoApprovalService:
    """خدمة القبول التلقائي"""

    @staticmethod
    def approve_pending_donations(hours_threshold=1):
        """
        قبول التبرعات المعلقة بعد ساعة واحدة

        Args:
            hours_threshold (int): عدد الساعات قبل القبول التلقائي (افتراضي: 1)

        Returns:
            dict: نتائج العملية
        """
        try:
            threshold_time = datetime.now(UTC) - timedelta(hours=hours_threshold)

            # جلب التبرعات المعلقة الأقدم من ساعة
            pending_donations = Donation.query.filter(
                Donation.status == "pending",
                Donation.transaction_type == "donation",
                Donation.created_at <= threshold_time,
            ).all()

            approved_count = 0
            approved_amount: float = 0

            for donation in pending_donations:
                donation.status = "completed"
                donation.completed_at = datetime.now(UTC)

                # تسجيل في Audit Log
                LoggingCore.log_audit(
                    action=f"auto_approved_donation: ${donation.amount_usd}",
                    table_name="donations",
                    record_id=donation.id,
                    changes={
                        "old_status": "pending",
                        "new_status": "completed",
                        "auto": True,
                    },
                )

                approved_count += 1
                approved_amount += float(donation.amount_usd or 0)

            with atomic_transaction("auto_approve_donations"):
                db.session.flush()

            if approved_count > 0:
                logger.info(f"✅ Auto-approved {approved_count} donations, total: ${approved_amount}")

            return {
                "success": True,
                "approved_count": approved_count,
                "approved_amount": approved_amount,
                "message": gettext(f"تم قبول {approved_count} تبرع تلقائياً"),
            }

        except Exception as e:
            logger.error(f"❌ Error in auto-approval: {str(e)}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def approve_pending_purchases(hours_threshold=1):
        """
        قبول المشتريات المعلقة بعد ساعة واحدة

        Args:
            hours_threshold (int): عدد الساعات قبل القبول التلقائي

        Returns:
            dict: نتائج العملية
        """
        try:
            threshold_time = datetime.now(UTC) - timedelta(hours=hours_threshold)

            # جلب المشتريات المعلقة الأقدم من ساعة
            pending_purchases = PackagePurchase.query.filter(
                PackagePurchase.payment_status == "pending",
                PackagePurchase.created_at <= threshold_time,
            ).all()

            approved_count = 0
            approved_amount: float = 0

            for purchase in pending_purchases:
                purchase.payment_status = "completed"
                purchase.activation_status = "activated"
                purchase.activation_date = datetime.now(UTC)

                # تحديث التبرع المرتبط
                related_donation = Donation.query.filter(
                    Donation.transaction_type == "purchase",
                    Donation.customer_email == purchase.customer_email,
                    Donation.package == purchase.package.slug,
                ).first()

                if related_donation and related_donation.status == "pending":
                    related_donation.status = "completed"
                    related_donation.completed_at = datetime.now(UTC)

                # تسجيل
                LoggingCore.log_audit(
                    action=f"auto_approved_purchase: {purchase.package.name_ar if purchase.package else 'N/A'}",
                    table_name="package_purchases",
                    record_id=purchase.id,
                    changes={
                        "old_status": "pending",
                        "new_status": "completed",
                        "auto": True,
                    },
                )

                approved_count += 1
                approved_amount += float(purchase.amount_paid or 0)

            with atomic_transaction("auto_approve_purchases"):
                db.session.flush()

            if approved_count > 0:
                logger.info(f"✅ Auto-approved {approved_count} purchases, total: ${approved_amount}")

            return {
                "success": True,
                "approved_count": approved_count,
                "approved_amount": approved_amount,
                "message": gettext(f"تم قبول {approved_count} مشترية تلقائياً"),
            }

        except Exception as e:
            logger.error(f"❌ Error in auto-approval purchases: {str(e)}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def run_auto_approval():
        """
        تشغيل القبول التلقائي لكل من التبرعات والمشتريات

        Returns:
            dict: نتائج العملية الكاملة
        """
        logger.info("🔄 Running auto-approval service...")

        # قبول التبرعات
        donations_result = AutoApprovalService.approve_pending_donations(hours_threshold=1)

        # قبول المشتريات
        purchases_result = AutoApprovalService.approve_pending_purchases(hours_threshold=1)

        return {
            "donations": donations_result,
            "purchases": purchases_result,
            "total_approved": donations_result.get("approved_count", 0) + purchases_result.get("approved_count", 0),
            "total_amount": donations_result.get("approved_amount", 0) + purchases_result.get("approved_amount", 0),
        }


# One scheduler per application instance. create_app() is called by the web
# process *and* by each Celery task, so the guard keeps a second worker thread
# from being spawned when the same app object is scheduled more than once.
_auto_approval_schedulers: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def schedule_auto_approval(app, stop_event=None, *, skip_if_scheduled=False):
    """Start the hourly auto-approval worker.

    Returns a handle ``{"thread": ..., "stop_event": ...}``. Passing a
    ``threading.Event`` lets the owner (the factory / web process) stop the
    worker cleanly on shutdown. Deployment callers pass
    ``skip_if_scheduled=True`` so a second call for the same app reuses the
    existing handle instead of spawning a duplicate thread.
    """
    import threading

    existing = _auto_approval_schedulers.get(app)
    if skip_if_scheduled and existing is not None:
        logger.info("Auto-approval scheduler already started for this app — skipping duplicate")
        return existing

    if stop_event is None:
        stop_event = threading.Event()

    def approval_task():
        # create_app() may run before the migration chain has been applied
        # (boot provisioning, Celery tasks). Give the schema time to come up
        # instead of querying it immediately at process start.
        if not stop_event.is_set():
            time.sleep(60)
        while not stop_event.is_set():
            try:
                with app.app_context():
                    result = AutoApprovalService.run_auto_approval()
                    logger.info(f"✅ Auto-approval completed: {result}")

            except Exception:
                logger.exception("Error in auto-approval task")
            finally:
                if not stop_event.is_set():
                    # الانتظار ساعة واحدة قبل التشغيل التالي
                    time.sleep(3600)  # 3600 ثانية = 1 ساعة

    thread = threading.Thread(target=approval_task, daemon=True)
    thread.start()
    handle = {"thread": thread, "stop_event": stop_event}
    _auto_approval_schedulers[app] = handle
    logger.info("✅ Auto-approval scheduler started")
    return handle
