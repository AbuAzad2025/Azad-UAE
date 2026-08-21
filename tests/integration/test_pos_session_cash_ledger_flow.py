"""Integration test: POS session close -> cash reconciliation -> GL."""

from __future__ import annotations

from decimal import Decimal

from models import GLJournalEntry
from services.sale_service import SaleService
from utils.db_safety import atomic_transaction
from utils.gl_reference_types import GLRef
from utils.pos_helpers import close_pos_session, create_pos_session


class TestPosSessionCashLedgerFlow:
    def test_pos_session_close_posts_variance_gl(
        self,
        app,
        db_session,
        demo_tenant,
        demo_branch,
        demo_warehouse,
        demo_user,
        demo_customer,
        demo_product_in_stock,
        demo_gl_accounts,
    ):
        """Closing a POS session with a cash variance posts a balanced GL entry."""
        opening_float = Decimal("100")
        unit_price = Decimal("100")
        quantity = Decimal("1")
        tax_rate = Decimal("5")
        sale_total = (unit_price * quantity * (Decimal("1") + tax_rate / Decimal("100"))).quantize(
            Decimal("0.001")
        )

        with app.app_context():
            with atomic_transaction("pos_session_open"):
                session = create_pos_session(
                    user=demo_user,
                    branch_id=demo_branch.id,
                    opening_balance=opening_float,
                )
                db_session.flush()

            lines = [
                {
                    "product": demo_product_in_stock,
                    "quantity": float(quantity),
                    "unit_price": float(unit_price),
                    "discount_percent": 0,
                }
            ]
            payment_data = {
                "amount": float(sale_total),
                "payment_method": "cash",
                "currency": "AED",
                "exchange_rate": 1.0,
            }

            with atomic_transaction("pos_session_cash_sale"):
                sale = SaleService.create_sale(
                    customer=demo_customer,
                    seller=demo_user,
                    lines_data=lines,
                    warehouse_id=demo_warehouse.id,
                    currency="AED",
                    tax_rate=tax_rate,
                    discount_amount=0,
                    shipping_cost=0,
                    payment_data=payment_data,
                )
                sale.pos_session_id = session.id
                session.total_cash_sales = Decimal(str(session.total_cash_sales or 0)) + sale_total
                session.total_sales = Decimal(str(session.total_sales or 0)) + sale_total
                db_session.add(session)
                db_session.flush()

            counted_cash = Decimal("200")  # Intentionally less than expected 205
            with atomic_transaction("pos_session_close"):
                close_pos_session(session, counted_cash, notes="Test close")
                db_session.flush()

        expected_balance = opening_float + sale_total
        expected_difference = counted_cash - expected_balance

        assert session.status == "closed"
        assert session.expected_balance == expected_balance
        assert session.difference == expected_difference

        # --- GL entry for variance exists and balances ---
        gl_entry = GLJournalEntry.query.filter_by(
            reference_type=GLRef.POS_CASH_DIFFERENCE,
            reference_id=session.id,
            tenant_id=demo_tenant.id,
        ).first()
        assert gl_entry is not None, "No POS_CASH_DIFFERENCE GL entry created"

        total_debit = sum(Decimal(str(line.debit or 0)) for line in gl_entry.lines)
        total_credit = sum(Decimal(str(line.credit or 0)) for line in gl_entry.lines)
        assert total_debit == total_credit, f"Variance GL entry unbalanced: {total_debit} != {total_credit}"
        assert total_debit == abs(expected_difference)

        # No cross-tenant leakage
        for line in gl_entry.lines:
            assert line.tenant_id == demo_tenant.id

    def test_pos_session_close_exact_count_no_variance_gl(
        self,
        app,
        db_session,
        demo_branch,
        demo_warehouse,
        demo_user,
        demo_customer,
        demo_product_in_stock,
        demo_gl_accounts,
    ):
        """Closing with exact cash count produces no variance and no GL entry."""
        opening_float = Decimal("50")
        unit_price = Decimal("100")
        quantity = Decimal("1")
        sale_total = unit_price * quantity

        with app.app_context():
            with atomic_transaction("pos_session_open_no_var"):
                session = create_pos_session(
                    user=demo_user,
                    branch_id=demo_branch.id,
                    opening_balance=opening_float,
                )
                db_session.flush()

            lines = [
                {
                    "product": demo_product_in_stock,
                    "quantity": float(quantity),
                    "unit_price": float(unit_price),
                    "discount_percent": 0,
                }
            ]
            payment_data = {
                "amount": float(sale_total),
                "payment_method": "cash",
                "currency": "AED",
                "exchange_rate": 1.0,
            }

            with atomic_transaction("pos_session_cash_sale_no_var"):
                sale = SaleService.create_sale(
                    customer=demo_customer,
                    seller=demo_user,
                    lines_data=lines,
                    warehouse_id=demo_warehouse.id,
                    currency="AED",
                    tax_rate=0,
                    discount_amount=0,
                    shipping_cost=0,
                    payment_data=payment_data,
                )
                sale.pos_session_id = session.id
                session.total_cash_sales = Decimal(str(session.total_cash_sales or 0)) + sale_total
                session.total_sales = Decimal(str(session.total_sales or 0)) + sale_total
                db_session.add(session)
                db_session.flush()

            expected_balance = opening_float + sale_total
            with atomic_transaction("pos_session_close_no_var"):
                close_pos_session(session, expected_balance)
                db_session.flush()

        assert session.difference == Decimal("0")
        gl_entry = GLJournalEntry.query.filter_by(
            reference_type=GLRef.POS_CASH_DIFFERENCE,
            reference_id=session.id,
        ).first()
        assert gl_entry is None
