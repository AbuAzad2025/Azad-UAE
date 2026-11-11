"""
خدمة الكفالات للصيانة - Warranty Service

إدارة حالات الكفالة مع تدقيق كامل لا يمكن حذفه.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from flask_babel import gettext
from sqlalchemy import or_

from extensions import db
from models import (
    Customer,
    MaintenanceDeviceRegistry,
    MaintenanceOrder,
    MaintenanceOrderWarrantyStatus,
    MaintenanceSetting,
    MaintenanceWarrantyAudit,
    User,
)
from utils.logger import log_financial
from utils.tenanting import tenant_query

logger = logging.getLogger(__name__)


def current_actor_id() -> int:
    """The acting user, or the platform anchor when there is no request.

    The audit trail names a person. A background job (a scheduled warranty
    sweep, a CLI call) has no ``current_user``, and the row must still say
    who acted, so the platform anchor stands in rather than the column
    being left null - which the schema forbids.
    """
    try:
        from flask_login import current_user

        if current_user is not None and getattr(current_user, "is_authenticated", False):
            return int(current_user.id)
    except Exception:
        logger.debug("No authenticated user in warranty audit context", exc_info=True)
    return 1


def _locked_order(order_id: int, tenant_id: int) -> MaintenanceOrder:
    order = (
        tenant_query(MaintenanceOrder)
        .filter_by(id=order_id, tenant_id=tenant_id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if order is None:
        raise ValueError(gettext("أمر الصيانة غير موجود"))
    if order.status in ("closed", "cancelled") or order.is_archived:
        raise ValueError(gettext("لا يمكن تغيير كفالة أمر منتهٍ"))
    return order


def _warranty_colors(tenant_id: int) -> dict[str, str]:
    """The tenant's warranty colour tags.

    The colours are the tenant's own choice (settings page), so the order
    row is tagged with the colour the tenant configured rather than a
    hardcoded one: two tenants running the same module can colour their
    counter differently.
    """
    setting = tenant_query(MaintenanceSetting).filter_by(tenant_id=tenant_id).first()
    return {
        "under_warranty": getattr(setting, "color_warranty", None) or "#10b981",
        "expired": getattr(setting, "color_non_warranty", None) or "#ef4444",
        "void": getattr(setting, "color_non_warranty", None) or "#ef4444",
        "unknown": getattr(setting, "color_unknown_warranty", None) or "#f59e0b",
    }


def _matching_device(order: MaintenanceOrder, tenant_id: int) -> MaintenanceDeviceRegistry | None:
    identifiers = []
    if order.device_serial_number:
        identifiers.append(MaintenanceDeviceRegistry.serial_number == order.device_serial_number)
    if order.device_imei:
        identifiers.append(MaintenanceDeviceRegistry.imei == order.device_imei)
    if order.device_plate:
        identifiers.append(MaintenanceDeviceRegistry.plate == order.device_plate)
    matches = (
        tenant_query(MaintenanceDeviceRegistry)
        .filter_by(tenant_id=tenant_id, is_active=True)
        .filter(or_(*identifiers))
        .populate_existing()
        .with_for_update()
        .limit(2)
        .all()
        if identifiers
        else []
    )
    if len(matches) > 1:
        raise ValueError(gettext("بيانات الجهاز غير متطابقة بشكل فريد"))
    device = matches[0] if matches else None
    if device:
        for submitted, recorded in (
            (order.device_serial_number, device.serial_number),
            (order.device_imei, device.imei),
            (order.device_plate, device.plate),
        ):
            if submitted and recorded and submitted != recorded:
                raise ValueError(gettext("بيانات الجهاز غير متطابقة بشكل فريد"))
        if device.customer_id and device.customer_id != order.customer_id:
            raise ValueError(gettext("لا يمكن تأكيد ملكية الجهاز لهذا العميل"))
    return device


def _change_warranty(order_id, tenant_id, performed_by, reason, *, restore):
    reason = (reason or "").strip()
    if not reason:
        raise ValueError(gettext("سبب تغيير الكفالة مطلوب"))
    actor = tenant_query(User).filter_by(id=performed_by, tenant_id=tenant_id, is_active=True).first()
    setting = tenant_query(MaintenanceSetting).filter_by(tenant_id=tenant_id).first()
    flag = "allow_engineer_restore_warranty" if restore else "allow_engineer_cancel_warranty"
    engineer_allowed = bool(setting and getattr(setting, flag) and actor and actor.has_permission("maintenance_work"))
    if actor is None or not (actor.has_permission("manage_maintenance") or engineer_allowed):
        raise ValueError(gettext("لا توجد صلاحية لتغيير الكفالة"))
    order = _locked_order(order_id, tenant_id)
    if not order.warranty_checked:
        raise ValueError(gettext("يجب فحص الكفالة أولاً"))
    device = _matching_device(order, tenant_id)
    if device is None:
        raise ValueError(gettext("الجهاز غير موجود في سجل الكفالات"))

    from_status = device.warranty_status
    if restore:
        last_change = (
            tenant_query(MaintenanceWarrantyAudit)
            .filter_by(tenant_id=tenant_id, maintenance_order_id=order.id)
            .filter(MaintenanceWarrantyAudit.action.in_(("cancelled", "restored")))
            .order_by(MaintenanceWarrantyAudit.id.desc())
            .first()
        )
        if device.is_under_warranty or last_change is None or last_change.action != "cancelled":
            raise ValueError(gettext("لا توجد كفالة ملغاة قابلة للاستعادة"))
        now = datetime.now(UTC)
        end = device.warranty_end_date
        start = device.warranty_start_date
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        if start and start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end is None or end < now or (start and start > now):
            raise ValueError(gettext("فترة الكفالة غير صالحة للاستعادة"))
        device.is_under_warranty = True
        to_status = MaintenanceOrderWarrantyStatus.UNDER_WARRANTY
        action = "restored"
        order.color_tag = _warranty_colors(tenant_id)["under_warranty"]
    else:
        if from_status != MaintenanceOrderWarrantyStatus.UNDER_WARRANTY:
            raise ValueError(gettext("لا توجد كفالة سارية للإلغاء"))
        device.is_under_warranty = False
        to_status = MaintenanceOrderWarrantyStatus.VOID
        action = "cancelled"
        order.color_tag = _warranty_colors(tenant_id)["void"]

    order.warranty_status = to_status
    order.warranty_checked_by = performed_by
    order.warranty_checked_at = datetime.now(UTC)
    audit = MaintenanceWarrantyAudit(
        tenant_id=tenant_id,
        maintenance_order_id=order.id,
        product_id=device.product_id,
        serial_number=order.device_serial_number,
        imei=order.device_imei,
        action=action,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        performed_by=performed_by,
    )
    db.session.add(audit)
    db.session.flush()
    return audit


class WarrantyService:
    """خدمة إدارة الكفالات - تدقيق كامل، لا حذف."""

    @staticmethod
    def check_warranty_on_receipt(
        order_id: int,
        tenant_id: int,
        *,
        checked_by: int,
    ) -> MaintenanceOrder:
        """فحص حالة الكفالة للجهاز عند الاستلام."""
        tid = tenant_id
        if not tenant_query(User).filter_by(id=checked_by, tenant_id=tid, is_active=True).first():
            raise ValueError(gettext("مستخدم فحص الكفالة غير موجود"))
        order = _locked_order(order_id, tid)
        device = _matching_device(order, tid)

        # تحديد حالة الكفالة
        warranty_status = MaintenanceOrderWarrantyStatus.UNKNOWN
        if device:
            ws = device.warranty_status  # special property on MaintenanceDeviceRegistry
            warranty_status = ws
            order.warranty_notes = device.warranty_notes
        else:
            # جهاز غير مسجل - غير معروف
            warranty_status = MaintenanceOrderWarrantyStatus.UNKNOWN

        previous_status = order.warranty_status
        order.warranty_status = warranty_status
        order.warranty_checked = True
        order.warranty_checked_by = checked_by
        order.warranty_checked_at = datetime.now(UTC)

        # تعيين لون التمييز (ألوان المستأجر من إعداداته)
        order.color_tag = _warranty_colors(tid).get(warranty_status, "#f59e0b")

        # سجل التدقيق
        audit = MaintenanceWarrantyAudit(
            tenant_id=tid,
            maintenance_order_id=order.id,
            product_id=device.product_id if device else None,
            serial_number=order.device_serial_number,
            imei=order.device_imei,
            action="checked",
            from_status=previous_status,
            to_status=warranty_status,
            reason=gettext("فحص الكفالة عند الاستلام"),
            performed_by=checked_by,
        )
        db.session.add(audit)
        db.session.flush()

        log_financial(
            message=f"Warranty checked: order {order.order_number} status {warranty_status}",
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_warranty_service.WarrantyService.check_warranty_on_receipt",
            extra={"order_id": order.id, "tenant_id": tid, "warranty_status": warranty_status},
        )

        return order

    @staticmethod
    def cancel_warranty(
        order_id: int,
        tenant_id: int,
        *,
        performed_by: int,
        reason: str | None,
    ) -> MaintenanceWarrantyAudit:
        """إلغاء كفالة المنتج."""
        return _change_warranty(order_id, tenant_id, performed_by, reason, restore=False)

    @staticmethod
    def restore_warranty(
        order_id: int,
        tenant_id: int,
        *,
        performed_by: int,
        reason: str | None,
    ) -> MaintenanceWarrantyAudit:
        """إعادة تفعيل الكفالة."""
        return _change_warranty(order_id, tenant_id, performed_by, reason, restore=True)

    @staticmethod
    def add_device_to_warranty_registry(
        tenant_id: int,
        *,
        performed_by: int | None = None,
        customer_id: int | None,
        product_id: int | None,
        brand: str | None,
        model: str | None,
        serial_number: str | None,
        imei: str | None,
        plate: str | None,
        purchase_date: datetime | None,
        warranty_start_date: datetime | None,
        warranty_end_date: datetime | None,
        warranty_type: str | None,
    ) -> MaintenanceDeviceRegistry:
        """إضافة جهاز إلى سجل الكفالات.

        The device registry is the module's memory of what it has seen: the
        same serial number, IMEI or plate on a later order is recognised as
        the same device and its warranty is read from here. So the
        identifiers have to be unique per tenant, and the record is written
        with an audit trail entry like every other warranty change.
        """
        tid = tenant_id
        if not any((serial_number, imei, plate)):
            raise ValueError(gettext("يجب إدخال رقم سيريال أو IMEI أو لوحة للجهاز"))

        for column, value in (
            ("serial_number", serial_number),
            ("imei", imei),
            ("plate", plate),
        ):
            if not value:
                continue
            existing = tenant_query(MaintenanceDeviceRegistry).filter_by(tenant_id=tid, **{column: value}).first()
            if existing is not None:
                raise ValueError(
                    gettext("الجهاز مسجل مسبقاً في سجل الكفالات ({column}: {value})").format(column=column, value=value)
                )

        if customer_id and not tenant_query(Customer).filter_by(id=customer_id, tenant_id=tid, is_active=True).first():
            raise ValueError(gettext("العميل غير موجود"))

        now = datetime.now(UTC)
        end = warranty_end_date
        if end is not None and end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        start = warranty_start_date
        if start is not None and start.tzinfo is None:
            start = start.replace(tzinfo=UTC)

        # The state the device is in right now. The flag on the row means
        # "not cancelled"; the dates decide whether the cover is live, has
        # run out, or was never given. A device registered with a period
        # that has already ended is EXPIRED, not VOID - a warranty only
        # becomes void when somebody cancels it.
        if end is None or (start is not None and start > now):
            status = MaintenanceOrderWarrantyStatus.UNKNOWN
        elif now > end:
            status = MaintenanceOrderWarrantyStatus.EXPIRED
        else:
            status = MaintenanceOrderWarrantyStatus.UNDER_WARRANTY

        device = MaintenanceDeviceRegistry(
            tenant_id=tid,
            customer_id=customer_id,
            product_id=product_id,
            brand=brand,
            model=model,
            serial_number=serial_number,
            imei=imei,
            plate=plate,
            purchase_date=purchase_date,
            warranty_start_date=warranty_start_date,
            warranty_end_date=warranty_end_date,
            warranty_type=warranty_type,
            is_under_warranty=True,
        )
        db.session.add(device)
        db.session.flush()

        db.session.add(
            MaintenanceWarrantyAudit(
                tenant_id=tid,
                maintenance_order_id=None,
                product_id=product_id,
                serial_number=serial_number,
                imei=imei,
                action="added",
                from_status=None,
                to_status=status,
                reason=gettext("إضافة جهاز إلى سجل الكفالات"),
                performed_by=performed_by if performed_by is not None else current_actor_id(),
            )
        )
        db.session.flush()

        log_financial(
            message=f"Device added to warranty registry: {serial_number or imei or plate}",
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_warranty_service.WarrantyService.add_device_to_warranty_registry",
            extra={"tenant_id": tid, "device_id": device.id},
        )

        return device

    @staticmethod
    def find_device_for_order(order_id: int, tenant_id: int) -> MaintenanceDeviceRegistry | None:
        """The registry record of the device on the order, if there is one.

        The counter needs to see whether the device is known before it can
        offer to register it, and the answer is read from the same lookup
        the warranty check uses - so the page and the check can never
        disagree about what is registered.
        """
        order = tenant_query(MaintenanceOrder).filter_by(id=order_id, tenant_id=tenant_id).first()
        if order is None:
            return None
        return _matching_device(order, tenant_id)

    @staticmethod
    def register_order_device(
        order_id: int,
        tenant_id: int,
        *,
        performed_by: int,
        warranty_start_date: datetime | None = None,
        warranty_end_date: datetime | None = None,
        warranty_type: str | None = None,
        purchase_date: datetime | None = None,
    ) -> MaintenanceDeviceRegistry:
        """تسجيل جهاز أمر الصيانة في سجل الكفالات.

        The device on the order is the device the module remembers: the
        identifiers are taken from the order itself, so the registry and the
        order can never disagree about which machine this is. Without this
        the warranty check would always answer "unknown", because there is
        nothing in the registry to compare the order against.
        """
        tid = tenant_id
        actor = tenant_query(User).filter_by(id=performed_by, tenant_id=tid, is_active=True).first()
        if actor is None:
            raise ValueError(gettext("المستخدم المنفّذ غير موجود"))

        order = (
            tenant_query(MaintenanceOrder)
            .filter_by(id=order_id, tenant_id=tid)
            .populate_existing()
            .with_for_update()
            .first()
        )
        if order is None:
            raise ValueError(gettext("أمر الصيانة غير موجود"))
        if order.is_archived:
            raise ValueError(gettext("لا يمكن تسجيل جهاز لأمر مؤرشف"))

        device = WarrantyService.add_device_to_warranty_registry(
            tid,
            performed_by=performed_by,
            customer_id=order.customer_id,
            product_id=None,
            brand=order.device_brand,
            model=order.device_model,
            serial_number=order.device_serial_number,
            imei=order.device_imei,
            plate=order.device_plate,
            purchase_date=purchase_date,
            warranty_start_date=warranty_start_date,
            warranty_end_date=warranty_end_date,
            warranty_type=warranty_type,
        )

        log_financial(
            message=f"Order device registered for warranty: order {order.order_number}",
            tenant_id=tid,
            level="INFO",
            source="services.maintenance_warranty_service.WarrantyService.register_order_device",
            extra={
                "order_id": order.id,
                "tenant_id": tid,
                "device_id": device.id,
                "performed_by": performed_by,
            },
        )

        return device
