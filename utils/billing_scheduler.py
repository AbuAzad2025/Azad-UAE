"""Subscription lifecycle scheduler — expiry detection, WhatsApp reminders, auto-suspension."""

import logging
from datetime import datetime, timezone, timedelta

from extensions import db
from utils.db_safety import atomic_transaction

logger = logging.getLogger(__name__)

REMINDER_WINDOW_DAYS = 3


def run_subscription_check() -> dict:
    """Scan all tenants for subscription expiry and act accordingly.

    Returns a summary dict with counts of reminded, suspended, and active tenants.
    """
    from models.tenant import Tenant

    now = datetime.now(timezone.utc)
    reminder_cutoff = now + timedelta(days=REMINDER_WINDOW_DAYS)

    tenants = (
        db.session.query(Tenant)
        .filter(Tenant.is_active)
        .filter(not Tenant.is_suspended)
        .filter(Tenant.subscription_plan_duration != "lifetime")
        .filter(Tenant.subscription_end.isnot(None))
        .all()
    )

    reminded = 0
    suspended = 0
    ok = 0

    for tenant in tenants:
        end = tenant.subscription_end
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        if end <= now:
            _suspend_tenant(tenant)
            suspended += 1
        elif end <= reminder_cutoff:
            _send_expiry_reminder(tenant)
            reminded += 1
        else:
            ok += 1

    logger.info(
        "Subscription check complete: %d reminded, %d suspended, %d active",
        reminded,
        suspended,
        ok,
    )
    return {
        "reminded": reminded,
        "suspended": suspended,
        "active": ok,
        "total": len(tenants),
    }


def _suspend_tenant(tenant):
    """Mark a tenant as suspended due to subscription expiry."""
    try:
        with atomic_transaction("subscription_auto_suspend"):
            tenant.is_active = False
            tenant.is_suspended = True
            tenant.suspension_reason = (
                f"Subscription expired on {tenant.subscription_end.isoformat()}"
            )
    except Exception as exc:
        logger.error("Failed to suspend tenant %s: %s", tenant.id, exc)


def _send_expiry_reminder(tenant):
    """Queue a WhatsApp reminder for a tenant nearing expiry."""
    try:
        from services.whatsapp_service import WhatsAppService

        admin_email = _get_tenant_admin_email(tenant.id)
        days_left = (tenant.subscription_end - datetime.now(timezone.utc)).days
        wa_number = _resolve_whatsapp_number()

        if not wa_number:
            logger.warning(
                "WhatsApp not configured — skipping reminder for tenant %s", tenant.id
            )
            return

        message = (
            f"مرحباً، تنبيه: اشتراككم في نظام أزاد ينتهي خلال {days_left} يوم. "
            f"يرجى التجديد لتجنب تعليق الخدمة."
        )
        result = WhatsAppService.send_custom_message(wa_number, message)
        if result.get("success"):
            logger.info(
                "Expiry reminder sent for tenant %s (%s)", tenant.id, admin_email
            )
        else:
            logger.warning(
                "Reminder failed for tenant %s: %s", tenant.id, result.get("error")
            )
    except Exception as exc:
        logger.error("Failed to send reminder for tenant %s: %s", tenant.id, exc)


def _get_tenant_admin_email(tenant_id: int) -> str:
    from models.user import User, Role
    from models.enums import RoleEnum

    admin = (
        db.session.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(
            User.tenant_id == tenant_id,
            Role.slug.in_(RoleEnum.company_admin_values()),
        )
        .order_by(User.id.asc())
        .first()
    )
    return admin.email if admin else ""


def _resolve_whatsapp_number() -> str:
    from flask import current_app
    import re

    raw = current_app.config.get("DEVELOPER_WHATSAPP", "")
    if not raw:
        from models.system_settings import SystemSettings

        try:
            settings = SystemSettings.get_current()
            raw = settings.get_custom_setting("developer_whatsapp") or ""
        except Exception:
            raw = ""
    digits = re.sub(r"\D+", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    return digits
