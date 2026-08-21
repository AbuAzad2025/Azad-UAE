"""StorePaymentMethod tenant isolation tests."""

from __future__ import annotations

import uuid

import pytest

from extensions import db
from models.store_payment_method import StorePaymentMethod
from services.store_payment_method_service import StorePaymentMethodService
from tests.factories import TenantFactory


@pytest.fixture
def sample_tenant2(db_session):
    """Create a second tenant for isolation testing."""
    tenant = TenantFactory()
    db_session.commit()
    return tenant


class TestStorePaymentMethodTenantIsolation:
    """Test that StorePaymentMethod properly isolates data across tenants."""

    def test_create_method_sets_tenant_id(self, db_session, sample_tenant, sample_user):
        """Creating a payment method should set the tenant_id."""
        method = StorePaymentMethodService.create_method(
            {
                "code": f"test_{uuid.uuid4().hex[:8]}",
                "name_ar": "طريقة اختبار",
                "name_en": "Test Method",
                "is_enabled": True,
            },
            tenant_id=sample_tenant.id,
        )
        assert method.tenant_id == sample_tenant.id

    def test_tenant_isolation_create(self, db_session, sample_tenant, sample_user, sample_tenant2):
        """Methods created in one tenant should not be visible in another."""
        # Create in tenant 1
        method1 = StorePaymentMethodService.create_method(
            {
                "code": f"tenant1_method_{uuid.uuid4().hex[:8]}",
                "name_ar": "طريقة المستأجر 1",
                "name_en": "Tenant 1 Method",
                "is_enabled": True,
            },
            tenant_id=sample_tenant.id,
        )

        # Create in tenant 2 with same code
        method2 = StorePaymentMethodService.create_method(
            {
                "code": f"tenant1_method_{uuid.uuid4().hex[:8]}",
                "name_ar": "طريقة المستأجر 2",
                "name_en": "Tenant 2 Method",
                "is_enabled": True,
            },
            tenant_id=sample_tenant2.id,
        )

        # Query from tenant 1
        found1 = StorePaymentMethodService.get_by_code(method1.code, tenant_id=sample_tenant.id)
        assert found1 is not None
        assert found1.tenant_id == sample_tenant.id
        assert found1.name_en == "Tenant 1 Method"

        # Query from tenant 2
        found2 = StorePaymentMethodService.get_by_code(method2.code, tenant_id=sample_tenant2.id)
        assert found2 is not None
        assert found2.tenant_id == sample_tenant2.id
        assert found2.name_en == "Tenant 2 Method"

        # Cross-tenant query should not find the other tenant's method
        cross = StorePaymentMethodService.get_by_code(method1.code, tenant_id=sample_tenant2.id)
        assert cross is None

        cross2 = StorePaymentMethodService.get_by_code(method2.code, tenant_id=sample_tenant.id)
        assert cross2 is None

    def test_list_all_tenant_isolation(self, db_session, sample_tenant, sample_user, sample_tenant2):
        """list_all should only return methods for the specified tenant."""
        # Create methods in both tenants
        StorePaymentMethodService.create_method(
            {"code": f"t1_m1_{uuid.uuid4().hex[:6]}", "name_ar": "ت1", "name_en": "T1", "is_enabled": True},
            tenant_id=sample_tenant.id,
        )
        StorePaymentMethodService.create_method(
            {"code": f"t2_m1_{uuid.uuid4().hex[:6]}", "name_ar": "ت2", "name_en": "T2", "is_enabled": True},
            tenant_id=sample_tenant2.id,
        )

        # List from tenant 1
        t1_methods = StorePaymentMethodService.list_all(tenant_id=sample_tenant.id)
        assert all(m.tenant_id == sample_tenant.id for m in t1_methods)

        # List from tenant 2
        t2_methods = StorePaymentMethodService.list_all(tenant_id=sample_tenant2.id)
        assert all(m.tenant_id == sample_tenant2.id for m in t2_methods)

    def test_ensure_defaults_tenant_isolation(self, db_session, sample_tenant, sample_user, sample_tenant2):
        """ensure_defaults should create defaults per tenant."""
        StorePaymentMethodService.ensure_defaults(tenant_id=sample_tenant.id)
        StorePaymentMethodService.ensure_defaults(tenant_id=sample_tenant2.id)

        t1_codes = {m.code for m in StorePaymentMethodService.list_all(tenant_id=sample_tenant.id)}
        t2_codes = {m.code for m in StorePaymentMethodService.list_all(tenant_id=sample_tenant2.id)}

        # Both tenants should have the default methods
        assert "cod" in t1_codes
        assert "cod" in t2_codes

        # Methods should be separate instances per tenant
        t1_cod = StorePaymentMethodService.get_by_code("cod", tenant_id=sample_tenant.id)
        t2_cod = StorePaymentMethodService.get_by_code("cod", tenant_id=sample_tenant2.id)
        assert t1_cod.tenant_id == sample_tenant.id
        assert t2_cod.tenant_id == sample_tenant2.id
        assert t1_cod.id != t2_cod.id

    def test_toggle_enabled_tenant_isolation(self, db_session, sample_tenant, sample_user, sample_tenant2):
        """toggle_enabled should only affect methods in the correct tenant."""
        method = StorePaymentMethodService.create_method(
            {
                "code": f"toggle_{uuid.uuid4().hex[:8]}",
                "name_ar": "طريقة اختبار",
                "name_en": "Test Method",
                "is_enabled": False,
            },
            tenant_id=sample_tenant.id,
        )

        # Enable from same tenant - should work
        updated = StorePaymentMethodService.toggle_enabled(method.id, True, tenant_id=sample_tenant.id)
        assert updated.is_enabled is True

        # Try to toggle from different tenant - should raise
        with pytest.raises(ValueError, match="غير موجودة"):
            StorePaymentMethodService.toggle_enabled(method.id, False, tenant_id=sample_tenant2.id)

    def test_update_method_tenant_isolation(self, db_session, sample_tenant, sample_user, sample_tenant2):
        """update_method should only affect methods in the correct tenant."""
        method = StorePaymentMethodService.create_method(
            {
                "code": f"update_{uuid.uuid4().hex[:8]}",
                "name_ar": "طريقة أصلية",
                "name_en": "Original Method",
                "is_enabled": True,
            },
            tenant_id=sample_tenant.id,
        )

        # Update from same tenant - should work
        updated = StorePaymentMethodService.update_method(method.id, {"name_ar": "محدث"}, tenant_id=sample_tenant.id)
        assert updated.name_ar == "محدث"

        # Try to update from different tenant - should raise
        with pytest.raises(ValueError, match="غير موجودة"):
            StorePaymentMethodService.update_method(method.id, {"name_ar": "محدث2"}, tenant_id=sample_tenant2.id)

    def test_delete_method_tenant_isolation(self, db_session, sample_tenant, sample_user, sample_tenant2):
        """delete_method should only affect methods in the correct tenant."""
        method = StorePaymentMethodService.create_method(
            {
                "code": f"delete_{uuid.uuid4().hex[:8]}",
                "name_ar": "طريقة للحذف",
                "name_en": "Method to Delete",
                "is_enabled": True,
            },
            tenant_id=sample_tenant.id,
        )

        # Delete from same tenant - should work
        StorePaymentMethodService.delete_method(method.id, tenant_id=sample_tenant.id)
        assert db.session.get(StorePaymentMethod, method.id) is None

        # Create another in tenant 2
        method2 = StorePaymentMethodService.create_method(
            {"code": f"delete2_{uuid.uuid4().hex[:8]}", "name_ar": "ح2", "name_en": "D2", "is_enabled": True},
            tenant_id=sample_tenant2.id,
        )

        # Try to delete from different tenant - should raise
        with pytest.raises(ValueError, match="غير موجودة"):
            StorePaymentMethodService.delete_method(method2.id, tenant_id=sample_tenant.id)

    def test_validate_for_checkout_tenant_isolation(self, db_session, sample_tenant, sample_user, sample_tenant2):
        """validate_for_checkout should only validate methods in the correct tenant."""
        method = StorePaymentMethodService.create_method(
            {"code": f"checkout_{uuid.uuid4().hex[:8]}", "name_ar": "دفع", "name_en": "Pay", "is_enabled": True},
            tenant_id=sample_tenant.id,
        )

        # Validate from same tenant - should work
        validated = StorePaymentMethodService.validate_for_checkout(method.code, tenant_id=sample_tenant.id)
        assert validated.id == method.id

        # Try to validate from different tenant - should raise
        with pytest.raises(ValueError, match="غير متاحة"):
            StorePaymentMethodService.validate_for_checkout(method.code, tenant_id=sample_tenant2.id)

    def test_list_for_checkout_tenant_isolation(self, db_session, sample_tenant, sample_user, sample_tenant2):
        """list_for_checkout should only return methods for the specified tenant."""
        StorePaymentMethodService.create_method(
            {"code": f"checkout_t1_{uuid.uuid4().hex[:6]}", "name_ar": "ت1", "name_en": "T1", "is_enabled": True},
            tenant_id=sample_tenant.id,
        )
        StorePaymentMethodService.create_method(
            {"code": f"checkout_t2_{uuid.uuid4().hex[:6]}", "name_ar": "ت2", "name_en": "T2", "is_enabled": True},
            tenant_id=sample_tenant2.id,
        )

        t1_methods = StorePaymentMethodService.list_for_checkout(tenant_id=sample_tenant.id)
        assert all(m.tenant_id == sample_tenant.id for m in t1_methods)

        t2_methods = StorePaymentMethodService.list_for_checkout(tenant_id=sample_tenant2.id)
        assert all(m.tenant_id == sample_tenant2.id for m in t2_methods)

    def test_duplicate_code_different_tenants_allowed(self, db_session, sample_tenant, sample_user, sample_tenant2):
        """Same code should be allowed in different tenants."""
        code = f"same_code_{uuid.uuid4().hex[:6]}"
        m1 = StorePaymentMethodService.create_method(
            {"code": code, "name_ar": "م1", "name_en": "M1", "is_enabled": True},
            tenant_id=sample_tenant.id,
        )
        m2 = StorePaymentMethodService.create_method(
            {"code": code, "name_ar": "م2", "name_en": "M2", "is_enabled": True},
            tenant_id=sample_tenant2.id,
        )

        assert m1.tenant_id == sample_tenant.id
        assert m2.tenant_id == sample_tenant2.id
        assert m1.code == m2.code

    def test_duplicate_code_same_tenant_raises(self, db_session, sample_tenant, sample_user):
        """Same code in same tenant should raise."""
        code = f"dup_{uuid.uuid4().hex[:6]}"
        StorePaymentMethodService.create_method(
            {"code": code, "name_ar": "طريقة أصلية", "name_en": "Original Method", "is_enabled": True},
            tenant_id=sample_tenant.id,
        )
        with pytest.raises(ValueError, match="مستخدم مسبقاً"):
            StorePaymentMethodService.create_method(
                {"code": code, "name_ar": "طريقة مكررة", "name_en": "Duplicate Method", "is_enabled": True},
                tenant_id=sample_tenant.id,
            )

    def test_builtin_methods_per_tenant(self, db_session, sample_tenant, sample_user, sample_tenant2):
        """Built-in methods should be created per tenant."""
        StorePaymentMethodService.ensure_defaults(tenant_id=sample_tenant.id)
        StorePaymentMethodService.ensure_defaults(tenant_id=sample_tenant2.id)

        # Both should have built-in methods
        t1_builtin = StorePaymentMethod.query.filter_by(tenant_id=sample_tenant.id, is_builtin=True).all()
        t2_builtin = StorePaymentMethod.query.filter_by(tenant_id=sample_tenant2.id, is_builtin=True).all()

        assert len(t1_builtin) == len(t2_builtin)
        assert all(m.is_builtin for m in t1_builtin)
        assert all(m.is_builtin for m in t2_builtin)
        assert all(m.tenant_id == sample_tenant.id for m in t1_builtin)
        assert all(m.tenant_id == sample_tenant2.id for m in t2_builtin)
