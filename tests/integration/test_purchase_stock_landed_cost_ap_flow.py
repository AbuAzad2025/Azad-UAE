"""Integration test: Purchase -> Stock -> Landed Cost -> AP flow."""

from __future__ import annotations

from decimal import Decimal

from models import GLJournalEntry, ProductWarehouseStock
from services.purchase_service import PurchaseService
from utils.db_safety import atomic_transaction
from utils.gl_reference_types import GLRef


class TestPurchaseStockLandedCostApFlow:
    def test_purchase_increases_stock_and_capitalizes_landed_cost_and_updates_ap(
        self,
        app,
        db_session,
        demo_tenant,
        demo_branch,
        demo_warehouse,
        demo_user,
        demo_supplier,
        demo_product,
        demo_gl_accounts,
    ):
        """A purchase receipt increases stock, capitalizes landed costs, and updates AP."""
        quantity = Decimal("10")
        unit_cost = Decimal("50")
        freight = Decimal("30")
        customs_duty = Decimal("20")
        tax_rate = Decimal("5")

        lines_data = [
            {
                "product_id": demo_product.id,
                "quantity": float(quantity),
                "unit_cost": float(unit_cost),
                "discount_percent": 0,
            }
        ]

        with atomic_transaction("purchase_stock_landed_cost_ap_flow"):
            purchase = PurchaseService.create_purchase(
                user=demo_user,
                supplier_data={"supplier_id": demo_supplier.id},
                lines_data=lines_data,
                warehouse_id=demo_warehouse.id,
                currency="AED",
                tax_rate=tax_rate,
                freight=freight,
                customs_duty=customs_duty,
            )
            db_session.flush()

        # Stock increased by received quantity
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
        assert pws.quantity == quantity

        # Invoice total: tax is applied to the merchandise subtotal only;
        # freight and customs duty are capitalized into inventory asset.
        subtotal = quantity * unit_cost
        inventory_debit = subtotal + freight + customs_duty
        expected_tax = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"))
        expected_total = subtotal + freight + customs_duty + expected_tax

        assert purchase.tenant_id == demo_tenant.id
        assert purchase.total_amount == expected_total
        gl_entry = GLJournalEntry.query.filter_by(
            reference_type=GLRef.PURCHASE,
            reference_id=purchase.id,
            tenant_id=demo_tenant.id,
        ).first()
        assert gl_entry is not None, "No PURCHASE GL entry created"

        total_debit = sum(Decimal(str(line.debit or 0)) for line in gl_entry.lines)
        total_credit = sum(Decimal(str(line.credit or 0)) for line in gl_entry.lines)
        assert total_debit == total_credit, f"PURCHASE GL entry unbalanced: {total_debit} != {total_credit}"

        inventory_lines = [
            line for line in gl_entry.lines if line.account and line.account.code == "1140"
        ]
        assert len(inventory_lines) == 1
        assert inventory_lines[0].debit == inventory_debit

        # Supplier AP balance matches invoice + landed cost
        db_session.refresh(demo_supplier)
        assert demo_supplier.get_balance_base() == expected_total

        # No cross-tenant leakage
        for line in gl_entry.lines:
            assert line.tenant_id == demo_tenant.id
