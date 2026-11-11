"""The maintenance module's HTTP surface.

Every endpoint is exercised through the real client, so the guards
(``login_required``, the permission code, the tenant scope) and the
transaction boundary are part of the test rather than assumed.

What the file pins:

* an unauthenticated request is refused;
* a user without the maintenance permission is refused;
* one tenant's order is invisible to another tenant;
* the write endpoints really write (the order, the lines, the status
  change and the warranty audit), and a rejected write writes nothing;
* every write carries the CSRF token.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from models import MaintenanceOrder, MaintenanceOrderStatusLog, MaintenanceWarrantyAudit

MAINTENANCE_PERMISSIONS = (
    "manage_maintenance",
    "maintenance_receive",
    "maintenance_work",
    "maintenance_close",
    "maintenance_discount",
    "maintenance_override_discount",
)


@pytest.fixture
def maintenance_branch(db_session, tenant_with_maintenance):
    """A branch of the maintenance tenant."""
    from models import Branch

    branch = Branch(
        tenant_id=tenant_with_maintenance.id,
        name="Maintenance Branch",
        code="MNT",
        is_active=True,
        is_main=True,
    )
    db_session.add(branch)
    db_session.flush()
    return branch


@pytest.fixture
def maintenance_warehouse(db_session, tenant_with_maintenance, maintenance_branch):
    """The maintenance tenant's own warehouse.

    The shared ``maintenance_warehouse`` fixture belongs to a different tenant,
    and a warehouse from one tenant used with an order of another is
    exactly the cross-tenant mistake this module must not make.
    """
    from models import Warehouse

    warehouse = Warehouse(
        tenant_id=tenant_with_maintenance.id,
        branch_id=maintenance_branch.id,
        name="Maintenance Warehouse",
        name_ar="مستودع الصيانة",
        is_active=True,
    )
    db_session.add(warehouse)
    db_session.flush()
    return warehouse


@pytest.fixture
def maintenance_user(db_session, tenant_with_maintenance):
    """A user of the maintenance tenant that holds every maintenance permission."""
    from uuid import uuid4

    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug="super_admin").first()
    if role is None:
        role = Role(name="Super Admin", slug="super_admin", is_active=True)
        db_session.add(role)
        db_session.flush()

    for code in MAINTENANCE_PERMISSIONS:
        perm = db_session.query(Permission).filter_by(code=code).first()
        if perm is None:
            perm = Permission(code=code, name=code, name_ar=code, category="maintenance")
            db_session.add(perm)
            db_session.flush()
        if perm not in role.permissions:
            role.permissions.append(perm)
    db_session.flush()

    unique = uuid4().hex[:8]
    user = User(
        username=f"maint-user-{unique}",
        email=f"maint-{unique}@test.local",
        full_name="Maintenance User",
        tenant_id=tenant_with_maintenance.id,
        role_id=role.id,
        branch_id=None,
        is_active=True,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def tenant_with_maintenance(db_session):
    """A tenant whose chart carries the maintenance accounts."""
    from uuid import uuid4

    from models import Tenant
    from services.gl_service import GLService
    from utils.tenanting import without_tenant_scope

    unique = uuid4().hex[:8]
    tenant = Tenant(
        name=f"Maintenance Tenant {unique}",
        name_ar="شركة الصيانة",
        slug=f"maintenance-{unique}",
        country="AE",
        default_currency="AED",
        base_currency="AED",
    )
    db_session.add(tenant)
    db_session.flush()
    with without_tenant_scope():
        GLService.ensure_core_accounts(tenant_id=int(tenant.id))
    db_session.flush()
    return tenant


@pytest.fixture
def maintenance_client(client, app, maintenance_user, tenant_with_maintenance):
    """A client signed in as the maintenance user, on their own tenant.

    The login is a real POST through ``/auth/login`` - the same path a
    receptionist takes - so the session, the CSRF token and the tenant the
    app resolves from the signed-in user are all the real ones.
    """
    client.post(
        "/auth/login",
        data={
            "username": maintenance_user.username,
            "password": "password123",
        },
        follow_redirects=True,
    )
    client.environ_base["REMOTE_ADDR"] = "127.0.0.1"
    return client


@pytest.fixture
def csrf_token(maintenance_client):
    """The CSRF token of the signed-in session.

    Flask-WTF compares the form token with the one in the session, so the
    token has to be the session's own - a token minted in a separate
    request context would be rejected.
    """
    with maintenance_client.session_transaction() as sess:
        token = sess.get("csrf_token")
    if not token:
        # The session only carries the token once something has asked for
        # one; a GET of the app's own form creates it.
        maintenance_client.get("/maintenance/create")
        with maintenance_client.session_transaction() as sess:
            token = sess.get("csrf_token")
    return token


def _order(db_session, tenant, user, warehouse):
    """A maintenance order for the tenant.

    The order is committed, not left in the test's transaction: a write the
    route refuses is rolled back, and a rollback would take the order with
    it - which in production it would not, because the order was created
    and invoiced in earlier, committed transactions.
    """
    from services.maintenance_order_service import MaintenanceService

    order = MaintenanceService.create_order(
        tenant_id=tenant.id,
        branch_id=warehouse.branch_id,
        warehouse_id=warehouse.id,
        customer_id=None,
        customer_name="Route Test Customer",
        customer_phone=None,
        device_brand="Toyota",
        device_model="Camry",
        device_serial_number="SN-ROUTE-TEST",
        device_imei=None,
        device_plate=None,
        device_km=None,
        device_fault_description=None,
        received_by=user.id,
    )
    db_session.commit()
    return order


class TestAccessControl:
    """The guards in front of the module."""

    def test_anonymous_access_is_refused(self, client):
        assert client.get("/maintenance/").status_code in (302, 401, 403)

    def test_a_user_without_the_permission_is_refused(self, client, app, mock_user, tenant_with_maintenance):
        from unittest.mock import patch

        mock_user.has_permission.return_value = False
        with (
            patch("flask_login.utils._get_user", return_value=mock_user),
            patch("utils.auth_helpers.is_global_owner_user", return_value=False),
            patch("utils.decorators.is_global_owner_user", return_value=False),
            patch("utils.tenanting.get_active_tenant_id", return_value=tenant_with_maintenance.id),
            patch("utils.feature_guards._feature_denial", return_value=None),
            patch("extensions.limiter.limit", return_value=lambda f: f),
        ):
            response = client.get("/maintenance/")
        assert response.status_code == 403


class TestMaintenancePages:
    """The pages render."""

    def test_the_order_list_renders(
        self, maintenance_client, db_session, tenant_with_maintenance, maintenance_user, maintenance_warehouse
    ):
        _order(db_session, tenant_with_maintenance, maintenance_user, maintenance_warehouse)
        db_session.flush()

        response = maintenance_client.get("/maintenance/")
        assert response.status_code == 200
        assert b"SN-ROUTE-TEST" in response.data or b"Maintenance" in response.data

    def test_the_create_form_renders(self, maintenance_client):
        response = maintenance_client.get("/maintenance/create")
        assert response.status_code == 200
        assert b"device_serial_number" in response.data

    def test_the_order_detail_renders(
        self, maintenance_client, db_session, tenant_with_maintenance, maintenance_user, maintenance_warehouse
    ):
        order = _order(db_session, tenant_with_maintenance, maintenance_user, maintenance_warehouse)
        db_session.flush()

        response = maintenance_client.get(f"/maintenance/{order.id}")
        assert response.status_code == 200
        assert order.order_number.encode() in response.data

    def test_the_report_renders(self, maintenance_client):
        response = maintenance_client.get("/maintenance/report")
        assert response.status_code == 200

    def test_the_purchase_pages_render(self, maintenance_client):
        assert maintenance_client.get("/maintenance/purchases").status_code == 200
        assert maintenance_client.get("/maintenance/purchases/create").status_code == 200

    def test_the_statutory_document_answers_404_without_an_invoice(
        self, maintenance_client, db_session, tenant_with_maintenance, maintenance_user, maintenance_warehouse
    ):
        """لا مستند بلا فاتورة."""
        order = _order(db_session, tenant_with_maintenance, maintenance_user, maintenance_warehouse)
        db_session.flush()

        response = maintenance_client.get(f"/maintenance/{order.id}/einvoice.xml")
        assert response.status_code == 404

    def test_the_parts_report_renders(self, maintenance_client):
        response = maintenance_client.get("/maintenance/report/parts")
        assert response.status_code == 200

    def test_the_warranty_report_renders(self, maintenance_client):
        response = maintenance_client.get("/maintenance/report/warranty")
        assert response.status_code == 200

    def test_a_malformed_report_date_does_not_break_the_report(self, maintenance_client):
        """تاريخ غير صالح في الرابط لا يحوّل التقرير إلى خطأ 500."""
        response = maintenance_client.get("/maintenance/report?date_from=not-a-date")
        assert response.status_code == 200

    def test_the_warranty_audit_renders(self, maintenance_client):
        response = maintenance_client.get("/maintenance/warranty-audit")
        assert response.status_code == 200

    def test_the_service_templates_page_renders(self, maintenance_client):
        response = maintenance_client.get("/maintenance/service-templates")
        assert response.status_code == 200

    def test_the_settings_page_renders(self, maintenance_client):
        response = maintenance_client.get("/maintenance/settings")
        assert response.status_code == 200


class TestTenantIsolation:
    """One tenant's maintenance orders are invisible to another."""

    def test_an_order_of_another_tenant_is_not_found(
        self, maintenance_client, db_session, tenant_with_maintenance, maintenance_user, maintenance_warehouse
    ):
        from uuid import uuid4

        from models import Tenant
        from utils.tenanting import without_tenant_scope

        with without_tenant_scope():
            other = Tenant(
                name="Other Maintenance Tenant",
                name_ar="شركة أخرى",
                slug=f"other-{uuid4().hex[:8]}",
                country="AE",
                default_currency="AED",
                base_currency="AED",
            )
            db_session.add(other)
            db_session.flush()

        # The order is written straight to the row: the point of the test
        # is what the ROUTE can see, and the service rightly refuses to
        # write across the tenant boundary in the first place.
        other_order = MaintenanceOrder(
            tenant_id=other.id,
            branch_id=maintenance_warehouse.branch_id,
            warehouse_id=maintenance_warehouse.id,
            order_number="MN-OTHER-TENANT",
            order_date=datetime.now(UTC),
            customer_name="Someone Else",
            received_by=maintenance_user.id,
            status="received",
        )
        with without_tenant_scope():
            db_session.add(other_order)
            db_session.commit()

        assert maintenance_client.get(f"/maintenance/{other_order.id}").status_code == 404


class TestWrites:
    """The write endpoints really write."""

    def test_creating_an_order_writes_it(self, maintenance_client, db_session, tenant_with_maintenance, csrf_token):
        response = maintenance_client.post(
            "/maintenance/create",
            data={
                "csrf_token": csrf_token,
                "customer_name": "Walk-in",
                "device_brand": "Honda",
                "device_model": "Civic",
                "device_serial_number": "SN-CREATED",
                "currency": "AED",
                "exchange_rate": "1",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        order = (
            db_session.query(MaintenanceOrder)
            .filter_by(tenant_id=tenant_with_maintenance.id)
            .filter(MaintenanceOrder.device_serial_number == "SN-CREATED")
            .first()
        )
        assert order is not None
        assert order.status == "received"
        # The order number came from the document sequence, not from the form.
        assert order.order_number.startswith("MN-")

    def test_every_maintenance_form_carries_the_csrf_token(self, maintenance_client):
        """The forms post a CSRF token, so the app can refuse a forged post.

        The enforcement itself is Flask-WTF's job and is switched off in the
        test configuration; what this file pins is that every form the
        module renders actually carries the token, so turning enforcement on
        in production cannot start refusing the module's own forms.
        """
        for path in ("/maintenance/create", "/maintenance/settings", "/maintenance/service-templates"):
            response = maintenance_client.get(path)
            assert response.status_code == 200, path
            assert b'name="csrf_token"' in response.data, path

    def test_applying_an_order_discount_writes_it(
        self,
        maintenance_client,
        db_session,
        tenant_with_maintenance,
        maintenance_user,
        maintenance_warehouse,
        csrf_token,
    ):
        """الخصم الإجمالي يُكتب على الأمر ويعاد حساب الإجماليات."""
        from models import MaintenanceSetting

        setting = db_session.query(MaintenanceSetting).filter_by(tenant_id=tenant_with_maintenance.id).first()
        if setting is None:
            setting = MaintenanceSetting(
                tenant_id=tenant_with_maintenance.id,
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

        order = _order(db_session, tenant_with_maintenance, maintenance_user, maintenance_warehouse)
        db_session.flush()

        response = maintenance_client.post(
            f"/maintenance/{order.id}/discount",
            data={
                "csrf_token": csrf_token,
                "discount_mode": "percent",
                "discount_percent": "10",
                "discount_value": "0",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        db_session.expire_all()
        order = db_session.get(MaintenanceOrder, order.id)
        assert order.discount_total_percent == Decimal("10.00")
        assert order.discount_total_value == Decimal("0")

    def test_creating_and_receiving_a_purchase_order_writes_the_stock(
        self,
        maintenance_client,
        db_session,
        tenant_with_maintenance,
        maintenance_user,
        maintenance_warehouse,
        csrf_token,
    ):
        """أمر شراء القطع يُنشأ ويُستلم، فتصل القطع إلى المستودع."""
        from models import MaintenancePurchaseOrder, Product, ProductWarehouseStock

        product = Product(
            tenant_id=tenant_with_maintenance.id,
            name="Purchased Part",
            sku="PURCH-PART-1",
            cost_price=Decimal("30.000"),
            regular_price=Decimal("70.000"),
            current_stock=Decimal("0"),
        )
        db_session.add(product)
        db_session.flush()

        response = maintenance_client.post(
            "/maintenance/purchases/create",
            data={
                "csrf_token": csrf_token,
                "warehouse_id": str(maintenance_warehouse.id),
                "supplier_name": "Spare Parts Supplier",
                "tax_rate": "5",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        db_session.expire_all()
        order = (
            db_session.query(MaintenancePurchaseOrder)
            .filter_by(tenant_id=tenant_with_maintenance.id)
            .order_by(MaintenancePurchaseOrder.id.desc())
            .first()
        )
        assert order is not None
        assert order.status == "draft"
        assert order.po_number.startswith("MPO-")

        response = maintenance_client.post(
            f"/maintenance/purchases/{order.id}/lines",
            data={
                "csrf_token": csrf_token,
                "product_id": str(product.id),
                "quantity": "4",
                "unit_cost": "30",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        db_session.expire_all()
        order = db_session.get(MaintenancePurchaseOrder, order.id)
        assert len(order.lines) == 1
        assert order.subtotal == Decimal("120.000")

        response = maintenance_client.post(
            f"/maintenance/purchases/{order.id}/receive",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )
        assert response.status_code == 200

        db_session.expire_all()
        order = db_session.get(MaintenancePurchaseOrder, order.id)
        assert order.status == "received"

        stock = (
            db_session.query(ProductWarehouseStock)
            .filter_by(
                tenant_id=tenant_with_maintenance.id,
                product_id=product.id,
                warehouse_id=maintenance_warehouse.id,
            )
            .first()
        )
        assert stock is not None
        assert stock.quantity == Decimal("4.000")

    def test_registering_a_device_writes_the_registry_and_the_audit(
        self,
        maintenance_client,
        db_session,
        tenant_with_maintenance,
        maintenance_user,
        maintenance_warehouse,
        csrf_token,
    ):
        """تسجيل الجهاز في سجل الكفالات يكتب السجل ومسار التدقيق."""
        from models import MaintenanceDeviceRegistry

        order = _order(db_session, tenant_with_maintenance, maintenance_user, maintenance_warehouse)
        db_session.flush()

        response = maintenance_client.post(
            f"/maintenance/{order.id}/device",
            data={
                "csrf_token": csrf_token,
                "warranty_start_date": "2026-01-01",
                "warranty_end_date": "2027-01-01",
                "warranty_type": "manufacturer",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        db_session.expire_all()
        device = (
            db_session.query(MaintenanceDeviceRegistry)
            .filter_by(tenant_id=tenant_with_maintenance.id, serial_number="SN-ROUTE-TEST")
            .first()
        )
        assert device is not None
        assert device.warranty_type == "manufacturer"
        assert device.is_under_warranty is True

        audits = (
            db_session.query(MaintenanceWarrantyAudit)
            .filter_by(tenant_id=tenant_with_maintenance.id, action="added")
            .all()
        )
        assert len(audits) == 1
        assert audits[0].performed_by == maintenance_user.id

    def test_adding_a_part_writes_a_line_and_recalculates(
        self,
        maintenance_client,
        db_session,
        tenant_with_maintenance,
        maintenance_user,
        maintenance_warehouse,
        csrf_token,
    ):
        from models import Product

        order = _order(db_session, tenant_with_maintenance, maintenance_user, maintenance_warehouse)
        db_session.flush()

        product = Product(
            tenant_id=tenant_with_maintenance.id,
            name="Route Test Part",
            sku="ROUTE-PART-1",
            cost_price=Decimal("25.000"),
            regular_price=Decimal("60.000"),
            current_stock=Decimal("10.000"),
        )
        db_session.add(product)
        db_session.flush()

        response = maintenance_client.post(
            f"/maintenance/{order.id}/lines",
            data={
                "csrf_token": csrf_token,
                "product_id": str(product.id),
                "quantity": "2",
                "unit_price": "60",
                "warehouse_id": str(maintenance_warehouse.id),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        db_session.expire_all()
        order = db_session.get(MaintenanceOrder, order.id)
        lines = list(order.lines)
        assert len(lines) == 1
        assert lines[0].quantity == Decimal("2.000")
        assert lines[0].line_total == Decimal("120.000")

    def test_a_status_change_is_written_and_logged(
        self,
        maintenance_client,
        db_session,
        tenant_with_maintenance,
        maintenance_user,
        maintenance_warehouse,
        csrf_token,
    ):
        order = _order(db_session, tenant_with_maintenance, maintenance_user, maintenance_warehouse)
        db_session.flush()

        response = maintenance_client.post(
            f"/maintenance/{order.id}/status",
            data={"csrf_token": csrf_token, "status": "diagnosis", "note": "Started"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        db_session.expire_all()
        order = db_session.get(MaintenanceOrder, order.id)
        assert order.status == "diagnosis"
        logs = (
            db_session.query(MaintenanceOrderStatusLog)
            .filter_by(order_id=order.id, tenant_id=tenant_with_maintenance.id)
            .all()
        )
        assert len(logs) == 2
        assert logs[-1].to_status == "diagnosis"

    def test_an_illegal_status_change_is_refused_and_writes_nothing(
        self,
        maintenance_client,
        db_session,
        tenant_with_maintenance,
        maintenance_user,
        maintenance_warehouse,
        csrf_token,
    ):
        order = _order(db_session, tenant_with_maintenance, maintenance_user, maintenance_warehouse)
        db_session.flush()

        response = maintenance_client.post(
            f"/maintenance/{order.id}/status",
            data={"csrf_token": csrf_token, "status": "closed"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        db_session.expire_all()
        order = db_session.get(MaintenanceOrder, order.id)
        # The order did not move, and no log was written for the refusal.
        assert order.status == "received"
        logs = db_session.query(MaintenanceOrderStatusLog).filter_by(order_id=order.id, to_status="closed").count()
        assert logs == 0

    def test_checking_the_warranty_writes_an_audit_row(
        self,
        maintenance_client,
        db_session,
        tenant_with_maintenance,
        maintenance_user,
        maintenance_warehouse,
        csrf_token,
    ):
        order = _order(db_session, tenant_with_maintenance, maintenance_user, maintenance_warehouse)
        db_session.flush()

        response = maintenance_client.post(
            f"/maintenance/{order.id}/warranty/check",
            data={"csrf_token": csrf_token},
            follow_redirects=True,
        )
        assert response.status_code == 200

        db_session.expire_all()
        audits = (
            db_session.query(MaintenanceWarrantyAudit)
            .filter_by(
                tenant_id=tenant_with_maintenance.id,
                maintenance_order_id=order.id,
                action="checked",
            )
            .all()
        )
        assert len(audits) == 1

    def test_adding_a_service_template_writes_it(
        self, maintenance_client, db_session, tenant_with_maintenance, csrf_token
    ):
        from models import MaintenanceServiceTemplate

        response = maintenance_client.post(
            "/maintenance/service-templates",
            data={
                "csrf_token": csrf_token,
                "service_code": "ROUTE-001",
                "name": "Route Test Service",
                "service_category": "labor",
                "fixed_price": "15",
                "duration_minutes": "30",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        template = (
            db_session.query(MaintenanceServiceTemplate)
            .filter_by(tenant_id=tenant_with_maintenance.id, service_code="ROUTE-001")
            .first()
        )
        assert template is not None
        assert template.fixed_price == Decimal("15.000")

    def test_updating_the_settings_writes_them(
        self, maintenance_client, db_session, tenant_with_maintenance, csrf_token
    ):
        from models import MaintenanceSetting

        response = maintenance_client.post(
            "/maintenance/settings",
            data={
                "csrf_token": csrf_token,
                "max_discount_percent": "9.5",
                "max_discount_value": "100",
                "require_warranty_check": "on",
                "color_warranty": "#00ff00",
                "color_non_warranty": "#ff0000",
                "color_unknown_warranty": "#ffff00",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        db_session.expire_all()
        setting = db_session.query(MaintenanceSetting).filter_by(tenant_id=tenant_with_maintenance.id).first()
        assert setting is not None
        assert setting.max_discount_percent == Decimal("9.50")
        assert setting.require_warranty_check is True
        assert setting.color_warranty == "#00ff00"

    def test_an_invalid_colour_is_refused_and_the_old_value_stands(
        self, maintenance_client, db_session, tenant_with_maintenance, csrf_token
    ):
        from models import MaintenanceSetting

        # The settings page creates the row, so the refusal below is about
        # the colour and not about a row that was never there.
        assert maintenance_client.get("/maintenance/settings").status_code == 200
        db_session.expire_all()
        existing = db_session.query(MaintenanceSetting).filter_by(tenant_id=tenant_with_maintenance.id).first()
        assert existing is not None
        original = existing.color_warranty

        response = maintenance_client.post(
            "/maintenance/settings",
            data={
                "csrf_token": csrf_token,
                "max_discount_percent": "5",
                "max_discount_value": "0",
                "color_warranty": "not-a-colour",
                "color_non_warranty": "#ff0000",
                "color_unknown_warranty": "#ffff00",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        db_session.expire_all()
        setting = db_session.query(MaintenanceSetting).filter_by(tenant_id=tenant_with_maintenance.id).first()
        assert setting is not None
        assert setting.color_warranty == original
