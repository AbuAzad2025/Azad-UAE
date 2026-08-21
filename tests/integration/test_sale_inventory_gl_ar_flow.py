"""Integration test: Sale -> Inventory -> GL -> AR flow."""

from __future__ import annotations

from decimal import Decimal

from models import GLJournalEntry, ProductWarehouseStock
from services.sale_service import SaleService
from services.stock_service import StockService
from utils.db_safety import atomic_transaction
from utils.gl_reference_types import GLRef


class TestSaleInventoryGlArFlow:
    def test_sale_decreases_stock_and_posts_balanced_gl_and_ar(
        self,
        app,
        db_session,
        demo_tenant,
        demo_branch,
        demo_warehouse,
        demo_user,
        demo_customer,
        demo_product,
        demo_gl_accounts,
    ):
        """A confirmed sale reduces stock, creates a balanced GL entry, and increases AR."""
        initial_stock = Decimal("10")
        StockService.add_stock(
            demo_product.id,
            float(initial_stock),
            warehouse_id=demo_warehouse.id,
        )
        db_session.flush()

        quantity = Decimal("3")
        unit_price = Decimal("100")
        tax_rate = Decimal("5")

        lines = [
            {
                "product": demo_product,
                "quantity": float(quantity),
                "unit_price": float(unit_price),
                "discount_percent": 0,
            }
        ]

        with atomic_transaction("sale_inventory_gl_ar_flow"):
            sale = SaleService.create_sale(
                customer=demo_customer,
                seller=demo_user,
                lines_data=lines,
                warehouse_id=demo_warehouse.id,
                currency="AED",
                tax_rate=tax_rate,
                discount_amount=0,
                shipping_cost=0,
            )
            db_session.flush()

        expected_subtotal = quantity * unit_price
        expected_tax = (expected_subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"))
        expected_total = expected_subtotal + expected_tax

        assert sale.tenant_id == demo_tenant.id
        assert sale.subtotal == expected_subtotal
        assert sale.total_amount == expected_total

        # --- Stock decreased by sold amount ---
        pws = (
            ProductWarehouseStock.query.filter_by(
                tenant_id=demo_tenant.id,
                product_id=demo_product.id,
                warehouse_id=demo_warehouse.id,
            )
            .order_by(ProductWarehouseStock.id.desc())
            .first()
        )
        assert pws is not None
        assert pws.quantity == initial_stock - quantity

        # --- GL journal entry exists and balances ---
        gl_entry = GLJournalEntry.query.filter_by(
            reference_type=GLRef.SALE,
            reference_id=sale.id,
            tenant_id=demo_tenant.id,
        ).first()
        assert gl_entry is not None, "No SALE GL entry created"

        total_debit = sum(Decimal(str(line.debit or 0)) for line in gl_entry.lines)
        total_credit = sum(Decimal(str(line.credit or 0)) for line in gl_entry.lines)
        assert total_debit == total_credit, f"SALE GL entry unbalanced: {total_debit} != {total_credit}"
        assert total_debit == expected_total

        # --- COGS entry exists and balances ---
        cogs_entry = GLJournalEntry.query.filter_by(
            reference_type=GLRef.SALE_COGS,
            reference_id=sale.id,
            tenant_id=demo_tenant.id,
        ).first()
        assert cogs_entry is not None, "No SALE_COGS GL entry created"
        cogs_debit = sum(Decimal(str(line.debit or 0)) for line in cogs_entry.lines)
        cogs_credit = sum(Decimal(str(line.credit or 0)) for line in cogs_entry.lines)
        assert cogs_debit == cogs_credit

        # --- No cross-tenant leakage in GL lines ---
        for line in gl_entry.lines:
            assert line.tenant_id == demo_tenant.id
        for line in cogs_entry.lines:
            assert line.tenant_id == demo_tenant.id

        # --- Customer AR balance increased by invoice total ---
        db_session.refresh(demo_customer)
        assert demo_customer.balance == -expected_total
