"""Gap coverage for models/warehouse.py — validator, type flags, reprs."""

from __future__ import annotations

import pytest

from models.warehouse import ProductWarehouseStock, Warehouse


class TestTenantValidator:
    def test_no_request_context_skips_lookup(self):
        wh = Warehouse(tenant_id=1, name="W1", branch_id=999)
        assert wh.tenant_id == 1

    def test_none_value_returns(self):
        wh = Warehouse(name="W2")
        wh.tenant_id = None
        assert wh.tenant_id is None

    def test_matching_branch_passes(self, app, db_session, sample_tenant, sample_branch):
        with app.test_request_context():
            wh = Warehouse(tenant_id=sample_tenant.id, name="W3")
            wh.branch_id = sample_branch.id
            wh.tenant_id = sample_tenant.id
            assert wh.tenant_id == sample_tenant.id

    def test_mismatched_branch_raises(self, app, db_session, sample_tenant):
        import uuid

        from models.branch import Branch
        from models.tenant import Tenant

        unique = uuid.uuid4().hex[:8]
        other_tenant = Tenant(name=f"Other {unique}", name_ar="أخرى", slug=f"other-{unique}", country="AE")
        db_session.add(other_tenant)
        db_session.flush()
        other_branch = Branch(tenant_id=other_tenant.id, name="Other", code=f"OT{unique[:4]}")
        db_session.add(other_branch)
        db_session.flush()
        with app.test_request_context():
            wh = Warehouse(tenant_id=sample_tenant.id, name="W4")
            wh.branch_id = other_branch.id
            with pytest.raises(ValueError, match="must match"):
                wh.tenant_id = sample_tenant.id

    def test_missing_branch_skips(self, app, db_session, sample_tenant):
        with app.test_request_context():
            wh = Warehouse(tenant_id=sample_tenant.id, name="W5")
            wh.branch_id = 999999999
            assert wh.tenant_id == sample_tenant.id


class TestTypeFlags:
    def test_online(self):
        assert Warehouse(warehouse_type="online").is_online is True
        assert Warehouse(warehouse_type="online").type_label_ar() == "أونلاين"

    def test_physical(self):
        assert Warehouse(warehouse_type="physical").is_online is False
        assert Warehouse(warehouse_type="physical").type_label_ar() == "فعلي"

    def test_none_defaults_physical(self):
        wh = Warehouse()
        wh.warehouse_type = None
        assert wh.is_online is False
        assert wh.type_label_ar() == "فعلي"

    def test_constants(self):
        assert Warehouse.TYPE_PHYSICAL == "physical"
        assert Warehouse.TYPE_ONLINE == "online"
        assert set(Warehouse.WAREHOUSE_TYPES) == {"physical", "online"}


class TestReprs:
    def test_warehouse_repr(self):
        assert "Main" in repr(Warehouse(name="Main"))

    def test_stock_repr(self):
        stock = ProductWarehouseStock(product_id=3, warehouse_id=8, quantity=12)
        text = repr(stock)
        assert "P#3" in text
        assert "W#8" in text
