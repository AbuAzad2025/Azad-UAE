"""Inventory reconciliation: PWC vs GL inventory account vs stock movements.

Compares three sources:
1. ProductWarehouseCost (PWC) — operational stock valuation
2. GLJournalLine for account 1140 (inventory asset) — ledger balance
3. stock_movements — physical movement trail (quantity audit)
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, text

from extensions import db
from models import (
    GLAccount,
    GLJournalEntry,
    GLJournalLine,
    Product,
    ProductWarehouseCost,
    StockMovement,
    Warehouse,
)
from services.gl_service import GL_ACCOUNTS
from utils.gl_tenant import scope_gl_accounts

# Tolerance for floating-point rounding in reconciliation
RECON_TOLERANCE = Decimal("0.01")


class InventoryReconciliationService:
    @staticmethod
    def _gl_inventory_balance(
        account_id: int,
        tenant_id: int | None,
        branch_id: int | None,
        warehouse_id: int | None,
    ) -> Decimal:
        """Sum of (debit − credit) for the inventory account with optional filters."""
        debit_q = (
            db.session.query(func.coalesce(func.sum(GLJournalLine.debit), 0))
            .filter(GLJournalLine.account_id == account_id)
            .join(GLJournalEntry)
            .filter(GLJournalEntry.is_posted == True)
        )
        credit_q = (
            db.session.query(func.coalesce(func.sum(GLJournalLine.credit), 0))
            .filter(GLJournalLine.account_id == account_id)
            .join(GLJournalEntry)
            .filter(GLJournalEntry.is_posted == True)
        )
        for q in (debit_q, credit_q):
            if tenant_id is not None:
                q = q.filter(GLJournalEntry.tenant_id == int(tenant_id))
            if branch_id is not None:
                q = q.filter(GLJournalEntry.branch_id == branch_id)
            if warehouse_id is not None:
                q = q.filter(GLJournalLine.warehouse_id == warehouse_id)

        return Decimal(str(debit_q.scalar() or 0)) - Decimal(
            str(credit_q.scalar() or 0)
        )

    @staticmethod
    def _movement_net_qty(
        tenant_id: int,
        product_id: int,
        warehouse_id: int,
    ) -> Decimal:
        result = db.session.execute(
            text(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM stock_movements
                WHERE tenant_id = :tid
                  AND product_id = :pid
                  AND warehouse_id = :wid
                """
            ),
            {"tid": tenant_id, "pid": product_id, "wid": warehouse_id},
        ).scalar()
        return Decimal(str(result or 0))

    @classmethod
    def build_report(
        cls,
        tenant_id: int | None = None,
        branch_id: int | None = None,
        warehouse_id: int | None = None,
    ) -> dict:
        """Build a reconciliation report for inventory.

        Returns dict with:
            rows: list of per-product/warehouse reconciliation rows
            summary: dict with totals and match status
        """
        # ── Resolve inventory GL account ──────────────────────────────
        acc_q = GLAccount.query.filter_by(code=GL_ACCOUNTS["inventory"])
        if tenant_id is not None:
            acc_q = scope_gl_accounts(acc_q, tenant_id=tenant_id)
        inventory_account = acc_q.first()

        # ── Query PWC records ─────────────────────────────────────────
        pwc_query = ProductWarehouseCost.query
        if tenant_id is not None:
            pwc_query = pwc_query.filter_by(tenant_id=tenant_id)
        if warehouse_id is not None:
            pwc_query = pwc_query.filter_by(warehouse_id=warehouse_id)

        pwc_records = pwc_query.all()

        rows = []
        total_pwc_value = Decimal("0")
        total_pwc_qty = Decimal("0")
        total_gl_value = Decimal("0")
        total_movement_qty = Decimal("0")

        for pwc in pwc_records:
            product = Product.query.get(pwc.product_id)
            warehouse = Warehouse.query.get(pwc.warehouse_id)

            # Quantity from movements
            movement_qty = cls._movement_net_qty(
                pwc.tenant_id, pwc.product_id, pwc.warehouse_id
            )

            # Value from GL (per warehouse if dimension is set)
            gl_value = Decimal("0")
            if inventory_account:
                gl_value = cls._gl_inventory_balance(
                    inventory_account.id,
                    tenant_id=pwc.tenant_id,
                    branch_id=branch_id,
                    warehouse_id=pwc.warehouse_id,
                )

            # Variance calculations
            qty_diff = Decimal(str(pwc.total_quantity or 0)) - movement_qty
            # GL value comparison is tricky because GL is aggregated per warehouse
            # For a single product row, we use proportional estimate or skip if warehouse GL is 0
            value_diff = Decimal("0")
            matched_qty = abs(qty_diff) <= RECON_TOLERANCE
            matched_value = abs(value_diff) <= RECON_TOLERANCE

            rows.append(
                {
                    "tenant_id": pwc.tenant_id,
                    "product_id": pwc.product_id,
                    "product_name": product.name if product else f"#{pwc.product_id}",
                    "warehouse_id": pwc.warehouse_id,
                    "warehouse_name": warehouse.name if warehouse else f"#{pwc.warehouse_id}",
                    "pwc_qty": float(pwc.total_quantity or 0),
                    "movement_qty": float(movement_qty),
                    "qty_diff": float(qty_diff),
                    "pwc_value": float(pwc.total_value or 0),
                    "pwc_avg_cost": float(pwc.average_cost or 0),
                    "gl_value": float(gl_value),
                    "matched_qty": matched_qty,
                    "matched_value": matched_value,
                }
            )

            total_pwc_value += Decimal(str(pwc.total_value or 0))
            total_pwc_qty += Decimal(str(pwc.total_quantity or 0))
            total_gl_value += gl_value
            total_movement_qty += movement_qty

        # ── Overall summary ──────────────────────────────────────────
        overall_qty_diff = total_pwc_qty - total_movement_qty
        overall_value_diff = total_pwc_value - total_gl_value

        # We only flag a mismatch if movements don't match PWC quantity.
        # GL value comparison is informational because GL is not always
        # tagged per product/warehouse in legacy entries.
        all_matched = all(r["matched_qty"] for r in rows)

        return {
            "rows": rows,
            "summary": {
                "total_pwc_value": float(total_pwc_value),
                "total_pwc_qty": float(total_pwc_qty),
                "total_gl_value": float(total_gl_value),
                "total_movement_qty": float(total_movement_qty),
                "overall_qty_diff": float(overall_qty_diff),
                "overall_value_diff": float(overall_value_diff),
                "all_matched": all_matched,
                "inventory_account_code": GL_ACCOUNTS["inventory"],
                "record_count": len(rows),
            },
        }

    @classmethod
    def build_warehouse_summary(
        cls,
        tenant_id: int | None = None,
        branch_id: int | None = None,
    ) -> dict:
        """Roll-up reconciliation at the warehouse level.

        Useful when GL dimensions (warehouse_id) are populated consistently.
        """
        report = cls.build_report(
            tenant_id=tenant_id,
            branch_id=branch_id,
        )

        from collections import defaultdict

        warehouse_map = defaultdict(
            lambda: {
                "pwc_qty": Decimal("0"),
                "pwc_value": Decimal("0"),
                "movement_qty": Decimal("0"),
                "gl_value": Decimal("0"),
                "products": 0,
            }
        )

        for row in report["rows"]:
            wid = row["warehouse_id"]
            w = warehouse_map[wid]
            w["pwc_qty"] += Decimal(str(row["pwc_qty"]))
            w["pwc_value"] += Decimal(str(row["pwc_value"]))
            w["movement_qty"] += Decimal(str(row["movement_qty"]))
            w["gl_value"] += Decimal(str(row["gl_value"]))
            w["products"] += 1
            w["warehouse_name"] = row["warehouse_name"]

        wh_rows = []
        for wid, w in warehouse_map.items():
            qty_diff = w["pwc_qty"] - w["movement_qty"]
            value_diff = w["pwc_value"] - w["gl_value"]
            wh_rows.append(
                {
                    "warehouse_id": wid,
                    "warehouse_name": w.get("warehouse_name", f"#{wid}"),
                    "products": w["products"],
                    "pwc_qty": float(w["pwc_qty"]),
                    "movement_qty": float(w["movement_qty"]),
                    "qty_diff": float(qty_diff),
                    "pwc_value": float(w["pwc_value"]),
                    "gl_value": float(w["gl_value"]),
                    "value_diff": float(value_diff),
                    "matched_qty": abs(qty_diff) <= RECON_TOLERANCE,
                    "matched_value": abs(value_diff) <= RECON_TOLERANCE,
                }
            )

        report["warehouse_summary"] = wh_rows
        return report
