from celery import Celery
from flask import current_app
import os
from utils.db_safety import atomic_transaction

celery = Celery(
    "azad_tasks",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Dubai",
    enable_utc=True,
    beat_schedule={
        "daily-inventory-reconciliation": {
            "task": "services.celery_tasks.run_inventory_reconciliation",
            "schedule": 86400.0,  # 24 hours in seconds
            "args": (None,),  # tenant_id=None → reconcile all tenants
        },
        "check-abandoned-carts": {
            "task": "services.celery_tasks.send_abandoned_cart_reminders",
            "schedule": 900.0,  # Every 15 minutes
        },
    },
)


@celery.task
def run_inventory_reconciliation(tenant_id: int | None = None):
    """Scheduled inventory reconciliation — logs mismatches for admin review."""
    from app import create_app
    from services.inventory_reconciliation_service import InventoryReconciliationService
    from extensions import db
    from models import ProductWarehouseCost
    import logging

    logger = logging.getLogger(__name__)
    app = create_app()
    with app.app_context():
        if tenant_id is None:
            tenant_ids = [
                row[0]
                for row in db.session.query(ProductWarehouseCost.tenant_id)
                .distinct()
                .order_by(ProductWarehouseCost.tenant_id)
                .all()
            ]
        else:
            tenant_ids = [tenant_id]

        results = []
        for tid in tenant_ids:
            report = InventoryReconciliationService.build_warehouse_summary(tenant_id=tid)
            summary = report["summary"]
            qty_ok = summary.get("all_matched_qty", summary.get("all_matched", False))
            value_ok = summary.get("all_matched_value", True)
            all_ok = qty_ok and value_ok

            qty_mismatches = [r for r in report["rows"] if not r["matched_qty"]]
            value_mismatches = [r for r in report.get("warehouse_summary", []) if not r["matched_value"]]

            if all_ok:
                logger.info(
                    f"[Reconciliation] tenant={tid} ALL MATCHED: "
                    f"{summary['record_count']} products, qty={summary['total_pwc_qty']}"
                )
            else:
                logger.warning(
                    f"[Reconciliation] tenant={tid} REVIEW: "
                    f"qty_mismatches={len(qty_mismatches)} "
                    f"value_mismatches={len(value_mismatches)} "
                    f"products={summary['record_count']}"
                )
                for r in qty_mismatches:
                    logger.warning(
                        f"  product={r['product_id']} warehouse={r['warehouse_id']} "
                        f"pwc={r['pwc_qty']:.3f} movement={r['movement_qty']:.3f} diff={r['qty_diff']:+.3f}"
                    )
                for r in value_mismatches:
                    logger.warning(
                        f"  warehouse={r['warehouse_id']} "
                        f"pwc_value={r['pwc_value']:.2f} gl_value={r['gl_value']:.2f} "
                        f"diff={r['value_diff']:+.2f}"
                    )

            results.append(
                {
                    "tenant_id": tid,
                    "all_matched": all_ok,
                    "all_matched_qty": qty_ok,
                    "all_matched_value": value_ok,
                    "record_count": summary["record_count"],
                    "total_pwc_qty": summary["total_pwc_qty"],
                    "total_movement_qty": summary["total_movement_qty"],
                    "total_gl_value": summary.get("total_gl_value", 0),
                    "overall_value_diff": summary.get("overall_value_diff", 0),
                }
            )

        if tenant_id is not None:
            return (
                results[0]
                if results
                else {
                    "tenant_id": tenant_id,
                    "all_matched": True,
                    "record_count": 0,
                }
            )

        return {
            "tenant_id": None,
            "all_matched": all(r["all_matched"] for r in results),
            "tenant_count": len(results),
            "results": results,
        }


@celery.task
def generate_monthly_report(month: int, year: int):
    """⚠ SAFETY-GUARDED: placeholder — no unscoped multi-tenant data access.

    The original implementation imported ``services.report_service.ReportService``
    which does **not exist** in this codebase, and ran an unscoped platform-wide
    query that could leak cross-tenant data.  Until a properly scoped
    per-tenant reporting service is built, this task is a no-op.
    """
    import logging

    logger = logging.getLogger(__name__)
    logger.warning(
        "generate_monthly_report(%d, %d) — disabled. No tenant-scoped ReportService is available yet.",
        month,
        year,
    )
    return {
        "success": False,
        "error": "Disabled: ReportService not implemented — use per-tenant reporting instead.",
    }


@celery.task
def send_invoice_email(sale_id: int):
    from app import create_app
    from models import Sale
    from flask_mail import Message
    from extensions import mail

    app = create_app()
    with app.app_context():
        sale = Sale.query.get(sale_id)
        if sale and sale.customer and sale.customer.email:
            msg = Message(
                subject=f"فاتورة رقم {sale.sale_number}",
                recipients=[sale.customer.email],
                body=f"تجدون في المرفق فاتورتكم رقم {sale.sale_number}",
            )
            mail.send(msg)
            return {"success": True}
        return {"success": False}


@celery.task
def auto_backup_database():
    from app import create_app
    from services.backup_service import BackupService

    app = create_app()
    with app.app_context():
        backup = BackupService.auto_backup_daily()
        return {"success": bool(backup), "backup": backup}


@celery.task
def update_exchange_rates():
    from app import create_app
    from services.currency_service import CurrencyService

    app = create_app()
    with app.app_context():
        result = CurrencyService.update_all_rates()
        return result


@celery.task
def train_neural_models():
    from app import create_app
    from ai_knowledge.neural_engine import get_neural_engine

    app = create_app()
    with app.app_context():
        neural = get_neural_engine()
        results = neural.train_all_models()
        return results


@celery.task
def send_payment_reminders():
    from app import create_app
    from models import Customer
    from services.whatsapp_service import WhatsAppService
    from decimal import Decimal

    app = create_app()
    with app.app_context():
        from flask import g

        customers = Customer.query.filter_by(is_active=True).all()
        # group by tenant to keep tenant context isolated
        by_tenant = {}
        for c in customers:
            by_tenant.setdefault(c.tenant_id, []).append(c)
        sent = 0

        for tid, tenant_customers in by_tenant.items():
            g.active_tenant_id = tid
            for customer in tenant_customers:
                balance = customer.get_balance_aed()
                if balance > Decimal("1000") and customer.phone:
                    result = WhatsAppService.send_payment_reminder(customer.phone, customer.name, float(balance))
                    if result.get("success"):
                        sent += 1

        return {"sent": sent, "total_checked": len(customers)}


@celery.task
def send_abandoned_cart_reminders():
    """Send reminders for abandoned carts (1h and 24h after creation)."""
    from datetime import datetime, timedelta, timezone
    from models.shop_abandoned_cart import ShopAbandonedCart
    from services.store_service import StoreService
    from extensions import db

    now = datetime.now(timezone.utc)

    first_reminder = ShopAbandonedCart.query.filter(
        ShopAbandonedCart.reminder_sent_at.is_(None),
        ShopAbandonedCart.created_at <= now - timedelta(hours=1),
        ShopAbandonedCart.recovered.is_(False),
    ).all()

    for ac in first_reminder:
        try:
            with atomic_transaction("abandoned_cart_first_reminder"):
                store = StoreService.get_tenant_store(ac.tenant_id)
                if not store or not store.email:
                    continue
                ac.reminder_sent_at = now
                ac.reminder_count = (ac.reminder_count or 0) + 1
                db.session.flush()
        except Exception:
            current_app.logger.exception("Abandoned cart first reminder failed")

    second_reminder = ShopAbandonedCart.query.filter(
        ShopAbandonedCart.reminder_sent_at.isnot(None),
        ShopAbandonedCart.created_at <= now - timedelta(hours=24),
        ShopAbandonedCart.recovered.is_(False),
        ShopAbandonedCart.reminder_count == 1,
    ).all()

    for ac in second_reminder:
        try:
            with atomic_transaction("abandoned_cart_second_reminder"):
                store = StoreService.get_tenant_store(ac.tenant_id)
                if not store or not store.email:
                    continue
                ac.reminder_sent_at = now
                ac.reminder_count = (ac.reminder_count or 0) + 1
                db.session.flush()
        except Exception:
            current_app.logger.exception("Abandoned cart second reminder failed")


@celery.task
def cleanup_old_cache():
    from extensions import cache

    try:
        cache.clear()
        return {"success": True, "message": "Cache cleared"}
    except Exception as e:
        return {"success": False, "error": str(e)}
