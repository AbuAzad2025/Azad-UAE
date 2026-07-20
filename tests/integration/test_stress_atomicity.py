"""
Integration Stress Test: Atomic Transaction Enforcement
Verifies that mid-transaction failures fully roll back all partial writes.
"""

import pytest
from decimal import Decimal
from unittest.mock import patch
from extensions import db


@pytest.fixture
def crm_permissions(db_session, sample_role):
    """Add CRM permissions to sample_role so CRM routes pass permission checks."""
    from models import Permission

    for code in ["crm.view", "crm.manage"]:
        p = Permission.query.filter_by(code=code).first()
        if p is None:
            p = Permission(code=code, name=code, name_ar=code, category="test")
            db_session.add(p)
            db_session.commit()
        if p not in sample_role.permissions:
            sample_role.permissions.append(p)
            db_session.commit()
    return sample_role


@pytest.fixture
def pos_setup(
    db_session,
    sample_tenant,
    sample_customer,
    sample_user,
    sample_product_with_stock,
    sample_warehouse,
):
    from models import PosSession, PosShift

    session = PosSession(
        tenant_id=sample_tenant.id,
        user_id=sample_user.id,
        branch_id=sample_warehouse.branch_id,
        session_number="STRESS-TEST-001",
        opening_balance_cash=Decimal("0"),
        status="open",
    )
    db_session.add(session)
    db_session.flush()

    # Checkout requires an open shift on top of the open session.
    shift = PosShift(
        tenant_id=sample_tenant.id,
        session_id=session.id,
        user_id=sample_user.id,
        shift_number="STRESS-SHIFT-001",
        starting_cash=Decimal("0"),
        status=PosShift.SHIFT_OPEN,
    )
    db_session.add(shift)
    db_session.commit()
    db_session.refresh(session)
    return {
        "tenant": sample_tenant,
        "customer": sample_customer,
        "user": sample_user,
        "product": sample_product_with_stock,
        "warehouse": sample_warehouse,
        "session": session,
        "shift": shift,
    }


class TestPosCheckoutAtomicity:
    """P0: POS checkout must fully roll back on any mid-transaction failure."""

    @staticmethod
    def _checkout_payload(setup):
        return {
            "customer_id": setup["customer"].id,
            "warehouse_id": setup["warehouse"].id,
            "lines": [
                {
                    "product_id": setup["product"].id,
                    "quantity": 2,
                    "discount_percent": 0,
                    "unit_price": 100.0,
                }
            ],
            "payment_method": "cash",
            "paid_amount": 210.0,
            "currency": "AED",
        }

    def test_checkout_rolls_back_on_commit_failure(
        self, app, logged_in_client, pos_setup
    ):
        """commit() failure rolls back sale, stock, and KDS order."""
        from models import Sale, PosKdsOrder

        setup = pos_setup
        sale_count_before = Sale.query.count()
        stock_before = Decimal(str(setup["product"].current_stock or "0"))
        kds_count_before = PosKdsOrder.query.count()

        payload = self._checkout_payload(setup)

        with patch(
            "routes.pos.db.session.commit",
            side_effect=Exception("Simulated DB failure"),
        ):
            resp = logged_in_client.post("/pos/api/checkout", json=payload)

        assert resp.status_code == 500

        db.session.expire_all()
        assert Sale.query.count() == sale_count_before, (
            "Sale leaked despite commit failure"
        )

        setup["product"] = type(setup["product"]).query.get(setup["product"].id)
        assert Decimal(str(setup["product"].current_stock or "0")) == stock_before, (
            "Stock was mutated despite rollback"
        )

        assert PosKdsOrder.query.count() == kds_count_before, (
            "KDS order leaked despite rollback"
        )

    def test_checkout_rolls_back_mid_block_after_flush(
        self, app, logged_in_client, pos_setup
    ):
        """Failure inside atomic block after flush rolls back via atomic_transaction rollback()."""
        from models import Sale, PosKdsOrder, GLJournalEntry

        setup = pos_setup
        sale_count_before = Sale.query.count()
        gl_count_before = GLJournalEntry.query.count()
        stock_before = Decimal(str(setup["product"].current_stock or "0"))
        PosKdsOrder.query.count()

        payload = self._checkout_payload(setup)

        # Use an internal mock that makes StockService.process_sale_lines raise
        # This simulates a failure AFTER the sale is created and flushed
        # but BEFORE the atomic_transaction commits.
        with patch(
            "services.sale_service.StockService.process_sale_lines",
            side_effect=Exception(
                "Simulated stock processing failure after sale created"
            ),
        ):
            resp = logged_in_client.post("/pos/api/checkout", json=payload)

        # Get response data for debugging
        resp_data = resp.get_json() if resp.is_json else None
        assert resp.status_code == 500, (
            f"Expected 500, got {resp.status_code}: {resp_data}"
        )

        db.session.expire_all()
        assert Sale.query.count() == sale_count_before, (
            "Sale leaked despite mid-block failure"
        )
        assert GLJournalEntry.query.count() == gl_count_before, (
            "GL entries leaked despite rollback"
        )

        setup["product"] = type(setup["product"]).query.get(setup["product"].id)
        assert Decimal(str(setup["product"].current_stock or "0")) == stock_before, (
            "Stock leaked despite rollback"
        )

    def test_checkout_rolls_back_on_flush_failure(
        self, app, logged_in_client, pos_setup
    ):
        """flush() failure inside atomic block rolls back everything."""
        from models import Sale

        setup = pos_setup
        sale_count_before = Sale.query.count()
        session_total_before = Decimal(str(setup["session"].total_sales or "0"))

        payload = self._checkout_payload(setup)

        with patch(
            "routes.pos.db.session.flush",
            side_effect=Exception("Simulated flush failure"),
        ):
            resp = logged_in_client.post("/pos/api/checkout", json=payload)

        assert resp.status_code == 500

        db.session.expire_all()
        assert Sale.query.count() == sale_count_before, (
            "Sale leaked despite flush failure"
        )

        setup["session"] = type(setup["session"]).query.get(setup["session"].id)
        assert (
            Decimal(str(setup["session"].total_sales or "0")) == session_total_before
        ), "Session total_sales was mutated despite failure"


class TestPurchaseDeleteAtomicity:
    """P0: Purchase delete must fully roll back on mid-transaction failure."""

    def test_purchase_delete_rolls_back_on_gl_failure(
        self, app, logged_in_client, sample_purchase
    ):
        """GL reversal failure inside atomic block rolls back all changes."""
        from models import Purchase, PurchaseLine, Supplier

        purchase_id = sample_purchase.id
        supplier_balance_before = Decimal("0")
        if sample_purchase.supplier:
            supplier_balance_before = Decimal(
                str(sample_purchase.supplier.get_balance_base() or "0")
            )
        purchase_count_before = Purchase.query.count()
        line_count_before = PurchaseLine.query.count()

        with patch(
            "services.gl_service.GLService.reverse_entry",
            side_effect=Exception("Simulated GL failure"),
        ):
            logged_in_client.post(
                f"/purchases/{purchase_id}/delete", follow_redirects=True
            )

        db.session.expire_all()
        assert Purchase.query.count() == purchase_count_before, (
            "Purchase was deleted despite GL failure"
        )
        assert PurchaseLine.query.count() == line_count_before, (
            "PurchaseLines were deleted despite GL failure"
        )

        if sample_purchase.supplier:
            refreshed_supplier = Supplier.query.get(sample_purchase.supplier.id)
            assert (
                Decimal(str(refreshed_supplier.get_balance_base() or "0"))
                == supplier_balance_before
            ), "Supplier balance was mutated despite rollback"

    def test_purchase_delete_rolls_back_on_supplier_failure(
        self, app, logged_in_client, sample_purchase
    ):
        """Supplier balance update failure rolls back GL reversal too."""
        from models import Purchase

        purchase_id = sample_purchase.id
        purchase_count_before = Purchase.query.count()

        # routes.purchases imports Supplier locally inside the delete view,
        # so patch the query attribute on the shared model class itself.
        # Do not follow the redirect: base.html's tenant_usage context
        # processor also reads Supplier.query and would see the mock.
        with patch("models.Supplier.query") as mock_query:
            mock_query.filter_by.return_value.first.side_effect = Exception(
                "Supplier lookup failure"
            )
            resp = logged_in_client.post(f"/purchases/{purchase_id}/delete")

        assert resp.status_code == 302
        mock_query.filter_by.assert_called()

        db.session.expire_all()
        assert Purchase.query.count() == purchase_count_before, (
            "Purchase was deleted despite supplier failure"
        )

    def test_purchase_archive_fallback_atomicity(
        self, app, logged_in_client, sample_purchase
    ):
        """Purchase archive fallback wraps in atomic, rolls back on flush failure."""
        from models import StockMovement
        from utils.gl_reference_types import GLRef
        from decimal import Decimal

        sm = StockMovement(
            tenant_id=sample_purchase.tenant_id,
            product_id=1,
            warehouse_id=1,
            movement_type="purchase",
            quantity=Decimal("10"),
            reference_type=GLRef.PURCHASE,
            reference_id=sample_purchase.id,
        )
        db.session.add(sm)
        db.session.commit()

        purchase_id = sample_purchase.id
        purchase_count_before = type(sample_purchase).query.count()

        with patch(
            "routes.purchases.db.session.flush",
            side_effect=Exception("Archive flush failure"),
        ):
            logged_in_client.post(
                f"/purchases/{purchase_id}/delete", follow_redirects=True
            )

        db.session.expire_all()
        assert type(sample_purchase).query.count() == purchase_count_before, (
            "Purchase was archived despite flush failure"
        )


class TestCrmAtomicity:
    """Atomicity verification for CRM write paths."""

    def test_create_lead_rolls_back_on_failure(
        self, app, logged_in_client, sample_tenant, sample_user, crm_permissions
    ):
        """Lead creation rolls back on flush failure."""
        from models.crm import CRMLead

        count_before = CRMLead.query.count()

        with patch(
            "utils.db_safety.db.session.flush",
            side_effect=Exception("Simulated lead creation failure"),
        ):
            logged_in_client.post(
                "/crm/leads/create",
                data={
                    "name": "Stress Test Lead",
                    "email": "stress@test.com",
                    "source": "website",
                    "stage_id": 1,
                },
                follow_redirects=True,
            )

        db.session.expire_all()
        assert CRMLead.query.count() == count_before, (
            "CRMLead was created despite flush failure"
        )

    def test_crm_stage_move_rolls_back(
        self, app, logged_in_client, db_session, sample_tenant, crm_permissions
    ):
        """Stage move inside atomic rolls back on exception."""
        from models.crm import CRMLead, CRMStage

        stage_a = CRMStage(tenant_id=sample_tenant.id, name="Stage A", sequence=1)
        stage_b = CRMStage(tenant_id=sample_tenant.id, name="Stage B", sequence=2)
        db_session.add(stage_a)
        db_session.add(stage_b)
        db_session.commit()

        lead = CRMLead(
            tenant_id=sample_tenant.id,
            name="Stage Test Lead",
            stage_id=stage_a.id,
            source="website",
        )
        db_session.add(lead)
        db_session.commit()

        lead_id = lead.id
        stage_a_id = lead.stage_id

        with patch(
            "services.crm_lead_service.db.session.flush",
            side_effect=ValueError("Stage move failure"),
        ):
            logged_in_client.post(
                "/crm/api/move-stage",
                json={
                    "lead_id": lead_id,
                    "stage_id": stage_b.id,
                },
            )

        db.session.expire_all()
        refreshed = CRMLead.query.get(lead_id)
        assert refreshed.stage_id == stage_a_id, "Stage was moved despite flush failure"


class TestExpenseAtomicity:
    """Atomicity verification for expense write paths."""

    def test_expense_create_rolls_back(
        self, app, logged_in_client, sample_expense_category, sample_user
    ):
        """Expense creation rolls back on flush failure."""
        from models import Expense

        count_before = Expense.query.count()

        with patch(
            "routes.expenses.db.session.flush",
            side_effect=Exception("Expense creation failure"),
        ):
            logged_in_client.post(
                "/expenses/create",
                data={
                    "category_id": sample_expense_category.id,
                    "description": "Stress test expense",
                    "amount": 1000,
                    "payment_method": "cash",
                },
            )

        db.session.expire_all()
        assert Expense.query.count() == count_before, (
            "Expense was created despite flush failure"
        )


class TestSupplierAtomicity:
    """Atomicity verification for supplier write paths."""

    def test_supplier_create_rolls_back(self, app, logged_in_client):
        """Supplier creation rolls back on commit failure."""
        from models import Supplier

        count_before = Supplier.query.count()

        with patch(
            "routes.suppliers.db.session.commit",
            side_effect=Exception("Supplier creation failure"),
        ):
            logged_in_client.post(
                "/suppliers/create",
                data={
                    "name": "Stress Test Supplier",
                    "email": "supplier@stress.com",
                    "phone": "0555000000",
                },
            )

        db.session.expire_all()
        assert Supplier.query.count() == count_before, (
            "Supplier was created despite commit failure"
        )
