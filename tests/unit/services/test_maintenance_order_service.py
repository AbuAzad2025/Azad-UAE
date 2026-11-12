"""
اختبارات وحدة خدمة الصيانة - Maintenance Service Unit Tests

تغطي:
- إنشاء أمر صيانة
- إضافة قطع وخدمات
- تغيير الحالات
- فحص الكفالة
- إغلاق الأمر وقبض المبلغ
- إرجاع القطع (مرتجع)
- عزل المستأجرين
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from models import (
    MaintenanceDeviceRegistry,
    MaintenanceDiscountMode,
    MaintenanceOrder,
    MaintenanceOrderWarrantyStatus,
    MaintenanceWarrantyAudit,
)
from services.maintenance_order_service import MaintenanceService


class TestMaintenanceOrderCreation:
    """إنشاء أوامر الصيانة."""

    def test_create_order_success(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_customer,
        sample_product,
        sample_warehouse,
    ):
        """إنشاء أمر صيانة بنجاح."""
        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=sample_customer.id,
            customer_name="عميل تجريبي",
            customer_phone="0500000000",
            device_brand="تويوتا",
            device_model="كامري",
            device_serial_number="SN123456",
            device_imei="IMEI987654321",
            device_plate="أ 1234",
            device_km=50000,
            device_fault_description="مشكلة في المحرك",
            received_by=sample_user.id,
            currency="AED",
            exchange_rate=Decimal("1"),
            prices_include_vat=True,
        )

        assert order.id is not None
        assert order.order_number.startswith("MN-")
        assert order.status == "received"
        assert order.warranty_status == MaintenanceOrderWarrantyStatus.UNKNOWN
        assert order.currency == "AED"
        assert order.exchange_rate == Decimal("1")
        assert order.prices_include_vat is True
        assert order.tenant_id == sample_tenant.id
        assert order.received_by == sample_user.id

        # التحقق من سجل الحالة
        assert len(order.status_logs) == 1
        assert order.status_logs[0].to_status == "received"
        assert order.status_logs[0].changed_by == sample_user.id

    def test_create_order_requires_tenant(self, db_session, sample_user):
        """فشل إنشاء أمر بدون معرف مستأجر."""
        with pytest.raises(ValueError, match="معرف المستأجر مطلوب"):
            MaintenanceService.create_order(
                tenant_id=None,
                branch_id=None,
                warehouse_id=None,
                customer_id=None,
                customer_name=None,
                customer_phone=None,
                device_brand=None,
                device_model=None,
                device_serial_number=None,
                device_imei=None,
                device_plate=None,
                device_km=None,
                device_fault_description=None,
                received_by=sample_user.id,
            )

    def test_tenant_isolation(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_customer,
        sample_warehouse,
    ):
        """عزل المستأجرين: أمر من تينانت A لا يظهر لتينانت B."""
        from models import Tenant

        # تينانت ثاني
        tenant_b = Tenant(
            name="Tenant B",
            name_ar="التينانت ب",
            slug="tenant-b",
            country="AE",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(tenant_b)
        db_session.flush()

        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=sample_customer.id,
            customer_name="عميل أ",
            customer_phone="0500000000",
            device_brand="تويوتا",
            device_model="كامري",
            device_serial_number="SN-ISOLATION",
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description="عطل تجريبي",
            received_by=sample_user.id,
        )

        # محاولة الوصول من تينانت ب
        order_b = (
            db_session.query(MaintenanceOrder).filter_by(tenant_id=tenant_b.id, order_number=order.order_number).first()
        )
        assert order_b is None, "تسرب بيانات بين المستأجرين!"


class TestMaintenanceOrderLines:
    """سطور قطع الصيانة."""

    def test_add_line_success(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_product,
        sample_warehouse,
        mocker,
    ):
        """إضافة سطر قطع إلى أمر."""
        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=None,
            customer_name="عميل قطع",
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number=None,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )

        mocker.patch.object(sample_user, "has_permission", return_value=True)
        line = MaintenanceService.add_line(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            quantity=Decimal("2"),
            unit_price=Decimal("100.000"),
            discount_percent=Decimal("10"),
            discount_value=Decimal("0"),
            discount_mode=MaintenanceDiscountMode.PERCENT,
            tax_rate=Decimal("5"),
            warehouse_id=sample_warehouse.id,
            actor_id=sample_user.id,
        )

        assert line.id is not None
        assert line.quantity == Decimal("2")
        assert line.unit_price == Decimal("100.000")
        # الخط بعد الخصم: 2 * 100 * (1 - 0.10) = 180
        assert line.line_total == Decimal("180.000")
        assert line.tax_amount == Decimal("9.000")  # 180 * 5%

    def test_add_line_product_not_found(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_warehouse,
    ):
        """فشل إضافة قطعة غير موجودة."""
        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=None,
            customer_name=None,
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number=None,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )

        with pytest.raises(ValueError, match="المنتج غير موجود"):
            MaintenanceService.add_line(
                order_id=order.id,
                tenant_id=sample_tenant.id,
                product_id=999999,
                quantity=Decimal("1"),
                unit_price=Decimal("10"),
                warehouse_id=sample_warehouse.id,
            )

    def test_add_line_invalid_status(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_product,
        sample_warehouse,
    ):
        """إضافة قطع لأمر مغلق يجب أن تفشل."""
        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=None,
            customer_name=None,
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number=None,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )
        # محاكاة أمر مغلق سابقاً دون تجاوز مسار الإغلاق المحاسبي.
        order.status = "closed"
        db_session.flush()

        with pytest.raises(ValueError, match="لا يمكن إضافة قطع"):
            MaintenanceService.add_line(
                order_id=order.id,
                tenant_id=sample_tenant.id,
                product_id=sample_product.id,
                quantity=Decimal("1"),
                unit_price=Decimal("10"),
                warehouse_id=sample_warehouse.id,
            )


class TestMaintenanceStatusTransition:
    """تغيير حالات أمر الصيانة."""

    def test_transition_received_to_diagnosis(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_warehouse,
    ):
        """الانتقال من استلام إلى تشخيص."""
        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=None,
            customer_name=None,
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number=None,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )

        assert order.status == "received"

        order = MaintenanceService.transition_status(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            to_status="diagnosis",
            changed_by=sample_user.id,
            note="بدأ الفحص",
        )

        assert order.status == "diagnosis"
        assert len(order.status_logs) == 2
        assert order.status_logs[-1].to_status == "diagnosis"
        assert order.status_logs[-1].changed_by == sample_user.id
        assert order.status_logs[-1].note == "بدأ الفحص"

    def test_transition_to_closed_sets_closed_by(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_warehouse,
    ):
        """لا يجوز إغلاق الأمر من مسار تغيير الحالة."""
        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=None,
            customer_name=None,
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number=None,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )
        with pytest.raises(ValueError, match="لا يمكن إغلاق"):
            MaintenanceService.transition_status(
                order_id=order.id,
                tenant_id=sample_tenant.id,
                to_status="closed",
                changed_by=sample_user.id,
            )
        assert order.status == "received"
        assert order.closed_by is None
        assert order.closed_at is None


class TestMaintenanceWarranty:
    """فحص الكفالة."""

    def test_check_warranty_unknown_device(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_warehouse,
    ):
        """فحص كفالة جهاز غير مسجل."""
        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=None,
            customer_name=None,
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number="UNKNOWN-SN",
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )

        order = MaintenanceService.check_warranty(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            checked_by=sample_user.id,
        )

        assert order.warranty_checked is True
        assert order.warranty_status == MaintenanceOrderWarrantyStatus.UNKNOWN
        assert order.warranty_checked_by == sample_user.id
        assert order.warranty_checked_at is not None

        # تحقق من سجل التدقيق
        audits = (
            db_session.query(MaintenanceWarrantyAudit)
            .filter_by(tenant_id=sample_tenant.id, maintenance_order_id=order.id)
            .all()
        )
        assert len(audits) == 1
        assert audits[0].action == "checked"
        assert audits[0].performed_by == sample_user.id


class TestMaintenanceOrderDiscount:
    """الخصم الإجمالي على الأمر — يحتاج صلاحية وحدّاً أقصى."""

    @pytest.fixture
    def discount_user(self, db_session, sample_user):
        """مستخدم يملك صلاحية الخصم pero ليس صلاحية التجاوز.

        The two permissions are separated deliberately: the cap is what the
        tenant configured, and going over it is a supervisor's decision.
        """
        from models import Permission, Role

        # A role of its own, never the shared super_admin row: the seeded
        # super_admin carries every maintenance permission, including the
        # override, and reusing it would hand this user the very permission
        # the test is about. The precondition is "has the discount
        # permission, does NOT have the override", so it has to be built.
        role = db_session.query(Role).filter_by(slug="discount-holder").first()
        if role is None:
            role = Role(name="Discount Holder", slug="discount-holder", is_active=True)
            db_session.add(role)
            db_session.flush()
        sample_user.role_id = role.id
        db_session.flush()

        for code in ("maintenance_discount",):
            perm = db_session.query(Permission).filter_by(code=code).first()
            if perm is None:
                perm = Permission(code=code, name=code, name_ar=code, category="maintenance")
                db_session.add(perm)
                db_session.flush()
            if perm not in role.permissions:
                role.permissions.append(perm)
        db_session.flush()

        override = db_session.query(Permission).filter_by(code="maintenance_override_discount").first()
        if override is not None and override in role.permissions:
            role.permissions.remove(override)
            db_session.flush()
        return sample_user

    def _order_with_a_line(self, db_session, tenant, user, warehouse):
        order = MaintenanceService.create_order(
            tenant_id=tenant.id,
            branch_id=warehouse.branch_id,
            warehouse_id=warehouse.id,
            customer_id=None,
            customer_name="Discount Customer",
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number=None,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=user.id,
        )
        return order

    def test_a_user_without_the_discount_permission_cannot_discount(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_warehouse,
    ):
        """من لا يملك صلاحية الخصم لا يستطيع تطبيق خصم على الأمر."""
        from models import Permission, Role

        # A role without the maintenance discount permission.
        role = db_session.query(Role).filter_by(slug="no-discount").first()
        if role is None:
            role = Role(name="No Discount", slug="no-discount", is_active=True)
            db_session.add(role)
            db_session.flush()
        perm = db_session.query(Permission).filter_by(code="maintenance_discount").first()
        if perm is not None and perm in role.permissions:
            role.permissions.remove(perm)
            db_session.flush()

        user = sample_user
        original_role_id = user.role_id
        user.role_id = role.id
        db_session.flush()

        order = self._order_with_a_line(db_session, sample_tenant, sample_user, sample_warehouse)

        try:
            with pytest.raises(ValueError, match="صلاحية"):
                MaintenanceService.set_order_discount(
                    order_id=order.id,
                    tenant_id=sample_tenant.id,
                    actor_id=user.id,
                    discount_percent=Decimal("10"),
                    discount_value=Decimal("0"),
                    discount_mode="percent",
                )
        finally:
            user.role_id = original_role_id
            db_session.flush()

        assert order.discount_total_percent == Decimal("0")

    def test_a_discount_over_the_cap_needs_the_override_permission(
        self,
        db_session,
        sample_tenant,
        discount_user,
        sample_warehouse,
    ):
        """الخصم فوق السقف مرفوض ما لم تكن هناك صلاحية التجاوز."""
        from models import MaintenanceSetting

        setting = db_session.query(MaintenanceSetting).filter_by(tenant_id=sample_tenant.id).first()
        if setting is None:
            setting = MaintenanceSetting(
                tenant_id=sample_tenant.id,
                max_discount_percent=Decimal("5"),
                max_discount_value=Decimal("0"),
                require_manager_approval_above_discount=True,
                allow_engineer_discount=False,
                require_warranty_check=False,
                allow_engineer_cancel_warranty=False,
                allow_engineer_restore_warranty=False,
            )
            db_session.add(setting)
        else:
            setting.max_discount_percent = Decimal("5")
            setting.max_discount_value = Decimal("0")
        db_session.flush()

        order = self._order_with_a_line(db_session, sample_tenant, discount_user, sample_warehouse)

        with pytest.raises(ValueError, match="الحد"):
            MaintenanceService.set_order_discount(
                order_id=order.id,
                tenant_id=sample_tenant.id,
                actor_id=discount_user.id,
                discount_percent=Decimal("50"),
                discount_value=Decimal("0"),
                discount_mode="percent",
            )
        assert order.discount_total_percent == Decimal("0")

    def test_a_discount_within_the_cap_is_applied_and_allocated(
        self,
        db_session,
        sample_tenant,
        discount_user,
        sample_warehouse,
        sample_product,
    ):
        """الخصم المسموح يُطبق على الأمر ويوزَّع على سطوره."""
        from models import MaintenanceSetting

        setting = db_session.query(MaintenanceSetting).filter_by(tenant_id=sample_tenant.id).first()
        if setting is None:
            setting = MaintenanceSetting(
                tenant_id=sample_tenant.id,
                max_discount_percent=Decimal("50"),
                max_discount_value=Decimal("0"),
                require_manager_approval_above_discount=True,
                allow_engineer_discount=True,
                require_warranty_check=False,
                allow_engineer_cancel_warranty=False,
                allow_engineer_restore_warranty=False,
            )
            db_session.add(setting)
        else:
            setting.max_discount_percent = Decimal("50")
            setting.max_discount_value = Decimal("0")
        db_session.flush()

        order = self._order_with_a_line(db_session, sample_tenant, discount_user, sample_warehouse)
        MaintenanceService.add_line(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            quantity=Decimal("2"),
            unit_price=Decimal("100"),
            warehouse_id=sample_warehouse.id,
            actor_id=discount_user.id,
        )
        subtotal = Decimal(str(order.subtotal or 0))
        assert subtotal == Decimal("200.000")

        order = MaintenanceService.set_order_discount(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            actor_id=discount_user.id,
            discount_percent=Decimal("10"),
            discount_value=Decimal("0"),
            discount_mode="percent",
        )

        assert order.discount_total_percent == Decimal("10.00")
        assert order.discount_total_value == Decimal("0")
        # The discount reduced the order by exactly a tenth, and the tax is
        # charged on what is left.
        assert order.subtotal == Decimal("200.000")
        net = Decimal("180.000")
        assert order.taxable_amount == net
        # The order's rate is the rate it was actually taxed at, so the
        # invoice can print the rate next to the amount.
        assert order.tax_rate == Decimal("5.00")
        expected_tax = (net * order.tax_rate / Decimal("100")).quantize(Decimal("0.001"))
        assert order.tax_amount == expected_tax
        assert order.total_amount == net + expected_tax
        # And the share that landed on the line is stored, so a return of
        # that line reverses the same share.
        line = list(order.lines)[0]
        assert line.aggregate_discount == Decimal("20.000")
        assert line.taxable_amount == net


class TestMaintenanceDeviceRegistry:
    """سجل الكفالات: تسجيل الجهاز ثم فحص الكفالة."""

    def _order(self, db_session, tenant, user, warehouse, serial):
        return MaintenanceService.create_order(
            tenant_id=tenant.id,
            branch_id=warehouse.branch_id,
            warehouse_id=warehouse.id,
            customer_id=None,
            customer_name="Registry Customer",
            customer_phone=None,
            device_brand="Toyota",
            device_model="Camry",
            device_serial_number=serial,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=user.id,
        )

    def test_registering_a_device_makes_the_warranty_checkable(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_warehouse,
    ):
        """جهاز غير مسجل لا كفالة له - وتسجيله يجعل الفحص يجد الكفالة."""
        from datetime import UTC, datetime, timedelta

        from services.maintenance_warranty_service import WarrantyService

        order = self._order(db_session, sample_tenant, sample_user, sample_warehouse, "REGISTRY-SN-1")
        db_session.flush()

        # Before the registration the device is unknown.
        order = MaintenanceService.check_warranty(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            checked_by=sample_user.id,
        )
        assert order.warranty_status == MaintenanceOrderWarrantyStatus.UNKNOWN

        now = datetime.now(UTC)
        device = WarrantyService.register_order_device(
            order.id,
            sample_tenant.id,
            performed_by=sample_user.id,
            warranty_start_date=now - timedelta(days=1),
            warranty_end_date=now + timedelta(days=365),
            warranty_type="manufacturer",
        )
        db_session.flush()

        assert device.serial_number == "REGISTRY-SN-1"
        assert device.is_under_warranty is True

        # The registration itself is in the audit trail.
        audits = db_session.query(MaintenanceWarrantyAudit).filter_by(tenant_id=sample_tenant.id, action="added").all()
        assert len(audits) == 1
        assert audits[0].performed_by == sample_user.id

        # And now the check finds the warranty.
        order = MaintenanceService.check_warranty(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            checked_by=sample_user.id,
        )
        assert order.warranty_status == MaintenanceOrderWarrantyStatus.UNDER_WARRANTY

    def test_registering_the_same_device_twice_is_refused(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_warehouse,
    ):
        """لا يُسجَّل الجهاز نفسه مرتين."""
        from services.maintenance_warranty_service import WarrantyService

        order = self._order(db_session, sample_tenant, sample_user, sample_warehouse, "REGISTRY-SN-2")
        db_session.flush()

        WarrantyService.register_order_device(
            order.id,
            sample_tenant.id,
            performed_by=sample_user.id,
        )
        db_session.flush()

        with pytest.raises(ValueError, match="مسجل مسبقاً"):
            WarrantyService.register_order_device(
                order.id,
                sample_tenant.id,
                performed_by=sample_user.id,
            )


class TestMaintenanceCloseAndCollect:
    """إغلاق الأمر وقبض المبلغ."""

    def test_close_and_collect_refuses_an_order_that_is_not_ready(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_warehouse,
        sample_customer,
    ):
        """لا يُغلق أمر لم يجه بعد، فلا يصدر قبض ولا فاتورة."""
        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=sample_customer.id,
            customer_name="عميل إغلاق",
            customer_phone="0500000000",
            device_brand=None,
            device_model=None,
            device_serial_number=None,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )
        with pytest.raises(ValueError, match="غير جاهز"):
            MaintenanceService.close_and_collect(
                order_id=order.id,
                tenant_id=sample_tenant.id,
                cashier_id=sample_user.id,
                payment_mode="cash",
                amount_received=order.total_amount,
            )
        assert order.status == "received"
        assert order.receipts == []
        assert order.invoice is None

    def test_close_and_collect_refuses_an_unsupported_payment_mode(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_warehouse,
    ):
        """طريقة دفع غير معروفة مرفوضة قبل أي مستند مالي."""
        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=None,
            customer_name=None,
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number=None,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )
        for status in ("diagnosis", "in_progress"):
            MaintenanceService.transition_status(
                order_id=order.id,
                tenant_id=sample_tenant.id,
                to_status=status,
                changed_by=sample_user.id,
            )
        MaintenanceService.check_warranty(order.id, sample_tenant.id, checked_by=sample_user.id)
        MaintenanceService.transition_status(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            to_status="ready",
            changed_by=sample_user.id,
        )

        with pytest.raises(ValueError, match="طريقة دفع غير مدعومة"):
            MaintenanceService.close_and_collect(
                order_id=order.id,
                tenant_id=sample_tenant.id,
                cashier_id=sample_user.id,
                payment_mode="gold_bar",
                amount_received=order.total_amount,
            )
        assert order.status == "ready"
        assert order.invoice is None

    def test_only_the_close_flow_may_close_an_order(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_warehouse,
    ):
        """شاشة تغيير الحالة لا تُغلق أمراً - الإقفال عبر الفاتورة والقبض فقط."""
        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=None,
            customer_name=None,
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number=None,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )
        for status in ("diagnosis", "in_progress"):
            MaintenanceService.transition_status(
                order_id=order.id,
                tenant_id=sample_tenant.id,
                to_status=status,
                changed_by=sample_user.id,
            )
        MaintenanceService.check_warranty(order.id, sample_tenant.id, checked_by=sample_user.id)
        MaintenanceService.transition_status(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            to_status="ready",
            changed_by=sample_user.id,
        )

        with pytest.raises(ValueError, match="لا يمكن إغلاق"):
            MaintenanceService.transition_status(
                order_id=order.id,
                tenant_id=sample_tenant.id,
                to_status="closed",
                changed_by=sample_user.id,
            )
        assert order.status == "ready"
        assert order.invoice is None
        assert order.closed_by is None


class TestMaintenanceServiceTemplates:
    """قوالب الخدمات الثابتة."""

    def test_ensure_default_templates(
        self,
        db_session,
        sample_tenant,
    ):
        """إنشاء قوالب الخدمات الافتراضية."""
        templates = MaintenanceService.ensure_default_service_templates(sample_tenant.id)
        assert len(templates) == 4

        # التحقق من عدم التكرار عند الاستدعاء مرة ثانية
        templates_again = MaintenanceService.ensure_default_service_templates(sample_tenant.id)
        assert len(templates_again) == 0

        # التحقق من وجود القوالب
        codes = [t.service_code for t in templates]
        assert "MECH-001" in codes
        assert "ELEC-001" in codes
        assert "LABOR-001" in codes
        assert "DIAG-001" in codes


class TestMaintenanceRevenueReport:
    """تقرير إيرادات الصيانة."""

    def test_revenue_report(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_warehouse,
        sample_customer,
    ):
        """تقرير الإيرادات."""
        MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=sample_customer.id,
            customer_name="عميل تقرير",
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number=None,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )
        report = MaintenanceService.get_revenue_report(
            tenant_id=sample_tenant.id,
            date_from=None,
            date_to=None,
        )

        assert report["tenant_id"] == sample_tenant.id
        assert report["invoice_count"] == 0
        assert report["total_revenue"] == 0
        assert report["total_paid"] == 0
        assert report["invoices"] == []


class TestMaintenancePartsReport:
    """تقرير القطع المصروفة."""

    def test_an_empty_workshop_reports_nothing(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_warehouse,
    ):
        report = MaintenanceService.get_parts_report(sample_tenant.id)
        assert report["tenant_id"] == sample_tenant.id
        assert report["line_count"] == 0
        assert report["total_quantity"] == Decimal("0")
        assert report["total_cost"] == Decimal("0")
        assert report["parts"] == []

    def test_issued_parts_are_reported_with_their_cost(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_warehouse,
        sample_product,
    ):
        """القطع المصروفة تظهر بالكمية والتكلفة."""
        from models import ProductWarehouseCost, ProductWarehouseStock

        product = sample_product
        db_session.add(
            ProductWarehouseStock(
                tenant_id=sample_tenant.id,
                product_id=product.id,
                warehouse_id=sample_warehouse.id,
                quantity=Decimal("10"),
            )
        )
        db_session.add(
            ProductWarehouseCost(
                tenant_id=sample_tenant.id,
                product_id=product.id,
                warehouse_id=sample_warehouse.id,
                total_quantity=Decimal("10"),
                total_value=Decimal("400"),
                average_cost=Decimal("40"),
            )
        )
        db_session.flush()

        order = MaintenanceService.create_order(
            tenant_id=sample_tenant.id,
            branch_id=sample_warehouse.branch_id,
            warehouse_id=sample_warehouse.id,
            customer_id=None,
            customer_name="Parts Report",
            customer_phone=None,
            device_brand=None,
            device_model=None,
            device_serial_number=None,
            device_imei=None,
            device_plate=None,
            device_km=None,
            device_fault_description=None,
            received_by=sample_user.id,
        )
        MaintenanceService.add_line(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            product_id=product.id,
            quantity=Decimal("2"),
            unit_price=Decimal("100"),
            warehouse_id=sample_warehouse.id,
            actor_id=sample_user.id,
        )
        for status in ("diagnosis", "in_progress"):
            MaintenanceService.transition_status(
                order.id, sample_tenant.id, to_status=status, changed_by=sample_user.id
            )
        MaintenanceService.check_warranty(order.id, sample_tenant.id, checked_by=sample_user.id)
        MaintenanceService.transition_status(order.id, sample_tenant.id, to_status="ready", changed_by=sample_user.id)
        MaintenanceService.close_and_collect(
            order_id=order.id,
            tenant_id=sample_tenant.id,
            cashier_id=sample_user.id,
            payment_mode="cash",
            amount_received=order.total_amount,
        )
        db_session.flush()

        report = MaintenanceService.get_parts_report(sample_tenant.id)
        assert report["line_count"] == 1
        assert report["total_quantity"] == Decimal("2.000")
        assert report["total_cost"] == Decimal("80.000")
        assert len(report["parts"]) == 1
        row = report["parts"][0]
        assert row["product_id"] == product.id
        assert row["quantity"] == Decimal("2.000")
        assert row["cost"] == Decimal("80.000")
        assert row["order_count"] == 1
        assert row["order_numbers"] == [order.order_number]


class TestMaintenanceWarrantyReport:
    """تقرير الكفالات."""

    def test_the_report_counts_the_devices_by_state(
        self,
        db_session,
        sample_tenant,
        sample_user,
        sample_customer,
    ):
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        covered = MaintenanceDeviceRegistry(
            tenant_id=sample_tenant.id,
            customer_id=sample_customer.id,
            serial_number="WARRANTY-REPORT-COVERED",
            warranty_start_date=now - timedelta(days=1),
            warranty_end_date=now + timedelta(days=10),
            is_under_warranty=True,
            is_active=True,
        )
        expired = MaintenanceDeviceRegistry(
            tenant_id=sample_tenant.id,
            customer_id=sample_customer.id,
            serial_number="WARRANTY-REPORT-EXPIRED",
            warranty_start_date=now - timedelta(days=100),
            warranty_end_date=now - timedelta(days=1),
            # The flag means "not cancelled" - a warranty that has simply
            # run out is expired, not void.
            is_under_warranty=True,
            is_active=True,
        )
        db_session.add_all([covered, expired])
        db_session.flush()

        report = MaintenanceService.get_warranty_report(sample_tenant.id)
        assert report["tenant_id"] == sample_tenant.id
        assert report["device_count"] == 2
        assert report["under_warranty"] == 1
        assert report["expired"] == 1
        assert report["void"] == 0
        assert len(report["devices"]) == 2
