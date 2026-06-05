"""Inventory reconciliation: PWC vs GL inventory account vs stock movements.

Compares three sources:
1. ProductWarehouseCost (PWC) — operational stock valuation
2. GLJournalLine for account 1140 (inventory asset) — ledger balance
3. stock_movements — physical movement trail (quantity audit)
"""
from __future__ import annotations

from collections import defaultdict
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
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> Decimal:
        """Sum of (debit − credit) for the inventory account with optional filters.

        BUG FIX: previous version used ``for q in (debit_q, credit_q): q = q.filter(...)``
        which reassigned the *loop variable* without mutating debit_q/credit_q.
        Filters were silently ignored.  Now we apply filters directly to both queries.
        """
        debit_q = (
            db.session.query(func.coalesce(func.sum(GLJournalLine.debit), 0))
            .filter(GLJournalLine.account_id == account_id)
            .join(GLJournalEntry)
            .filter(GLJournalEntry.is_posted.is_(True))
        )
        credit_q = (
            db.session.query(func.coalesce(func.sum(GLJournalLine.credit), 0))
            .filter(GLJournalLine.account_id == account_id)
            .join(GLJournalEntry)
            .filter(GLJournalEntry.is_posted.is_(True))
        )
        if tenant_id is not None:
            debit_q = debit_q.filter(GLJournalEntry.tenant_id == int(tenant_id))
            credit_q = credit_q.filter(GLJournalEntry.tenant_id == int(tenant_id))
        if branch_id is not None:
            debit_q = debit_q.filter(GLJournalEntry.branch_id == branch_id)
            credit_q = credit_q.filter(GLJournalEntry.branch_id == branch_id)
        if warehouse_id is not None:
            debit_q = debit_q.filter(GLJournalLine.warehouse_id == warehouse_id)
            credit_q = credit_q.filter(GLJournalLine.warehouse_id == warehouse_id)
        if date_from:
            debit_q = debit_q.filter(GLJournalEntry.entry_date >= date_from)
            credit_q = credit_q.filter(GLJournalEntry.entry_date >= date_from)
        if date_to:
            debit_q = debit_q.filter(GLJournalEntry.entry_date <= date_to)
            credit_q = credit_q.filter(GLJournalEntry.entry_date <= date_to)

        return Decimal(str(debit_q.scalar() or 0)) - Decimal(
            str(credit_q.scalar() or 0)
        )

    @staticmethod
    def _movement_net_qty(
        tenant_id: int,
        product_id: int,
        warehouse_id: int,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> Decimal:
        sql = """
            SELECT COALESCE(SUM(quantity), 0)
            FROM stock_movements
            WHERE tenant_id = :tid
              AND product_id = :pid
              AND warehouse_id = :wid
        """
        params = {"tid": tenant_id, "pid": product_id, "wid": warehouse_id}
        if date_from:
            sql += " AND created_at >= :df"
            params["df"] = date_from
        if date_to:
            sql += " AND created_at <= :dt"
            params["dt"] = date_to
        result = db.session.execute(text(sql), params).scalar()
        return Decimal(str(result or 0))

    @classmethod
    def build_report(
        cls,
        tenant_id: int | None = None,
        branch_id: int | None = None,
        warehouse_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        """Build a reconciliation report for inventory.

        Per-product rows compare PWC.quantity vs stock_movements.net_qty ONLY.
        GL value is **not** shown per-product because GL 1140 tracks aggregate
        warehouse-level balances, not per-product values.  GL comparison happens
        at the warehouse-summary level (build_warehouse_summary).
        """
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
        total_movement_qty = Decimal("0")

        for pwc in pwc_records:
            product = Product.query.get(pwc.product_id)
            warehouse = Warehouse.query.get(pwc.warehouse_id)

            movement_qty = cls._movement_net_qty(
                pwc.tenant_id,
                pwc.product_id,
                pwc.warehouse_id,
                date_from=date_from,
                date_to=date_to,
            )

            qty_diff = Decimal(str(pwc.total_quantity or 0)) - movement_qty
            matched_qty = abs(qty_diff) <= RECON_TOLERANCE

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
                    "matched_qty": matched_qty,
                }
            )

            total_pwc_value += Decimal(str(pwc.total_value or 0))
            total_pwc_qty += Decimal(str(pwc.total_quantity or 0))
            total_movement_qty += movement_qty

        overall_qty_diff = total_pwc_qty - total_movement_qty
        all_matched = all(r["matched_qty"] for r in rows)

        return {
            "rows": rows,
            "summary": {
                "total_pwc_value": float(total_pwc_value),
                "total_pwc_qty": float(total_pwc_qty),
                "total_movement_qty": float(total_movement_qty),
                "overall_qty_diff": float(overall_qty_diff),
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
        warehouse_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        """Roll-up reconciliation at the warehouse level.

        GL balance is fetched **once per warehouse** (not once per product),
        eliminating the double-counting bug present in the original implementation.
        """
        report = cls.build_report(
            tenant_id=tenant_id,
            branch_id=branch_id,
            warehouse_id=warehouse_id,
            date_from=date_from,
            date_to=date_to,
        )

        # Resolve inventory GL account once
        acc_q = GLAccount.query.filter_by(code=GL_ACCOUNTS["inventory"])
        if tenant_id is not None:
            acc_q = scope_gl_accounts(acc_q, tenant_id=tenant_id)
        inventory_account = acc_q.first()

        # Aggregate PWC / movement data per warehouse from product rows
        warehouse_map = defaultdict(
            lambda: {
                "pwc_qty": Decimal("0"),
                "pwc_value": Decimal("0"),
                "movement_qty": Decimal("0"),
                "products": 0,
                "warehouse_name": "",
            }
        )

        for row in report["rows"]:
            wid = row["warehouse_id"]
            w = warehouse_map[wid]
            w["pwc_qty"] += Decimal(str(row["pwc_qty"]))
            w["pwc_value"] += Decimal(str(row["pwc_value"]))
            w["movement_qty"] += Decimal(str(row["movement_qty"]))
            w["products"] += 1
            w["warehouse_name"] = row["warehouse_name"]

        # Fetch GL balance ONCE per warehouse and build summary rows
        wh_rows = []
        for wid, w in warehouse_map.items():
            gl_value = Decimal("0")
            gl_untagged = False
            if inventory_account:
                gl_value = cls._gl_inventory_balance(
                    inventory_account.id,
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    warehouse_id=wid,
                    date_from=date_from,
                    date_to=date_to,
                )
                # If warehouse-filtered GL is 0 but PWC has value, legacy entries
                # may lack warehouse_id dimension.  Flag this for the UI.
                if gl_value == 0 and w["pwc_value"] > 0:
                    total_gl = cls._gl_inventory_balance(
                        inventory_account.id,
                        tenant_id=tenant_id,
                        branch_id=branch_id,
                        warehouse_id=None,
                        date_from=date_from,
                        date_to=date_to,
                    )
                    if total_gl != 0:
                        gl_untagged = True

            qty_diff = w["pwc_qty"] - w["movement_qty"]
            value_diff = w["pwc_value"] - gl_value
            wh_rows.append(
                {
                    "warehouse_id": wid,
                    "warehouse_name": w["warehouse_name"] or f"#{wid}",
                    "products": w["products"],
                    "pwc_qty": float(w["pwc_qty"]),
                    "movement_qty": float(w["movement_qty"]),
                    "qty_diff": float(qty_diff),
                    "pwc_value": float(w["pwc_value"]),
                    "gl_value": float(gl_value),
                    "value_diff": float(value_diff),
                    "matched_qty": abs(qty_diff) <= RECON_TOLERANCE,
                    "matched_value": abs(value_diff) <= RECON_TOLERANCE,
                    "gl_untagged": gl_untagged,
                }
            )

        # Overall totals from warehouse summary (no double-counting)
        total_gl_value = sum(Decimal(str(r["gl_value"])) for r in wh_rows)
        total_pwc_value = sum(Decimal(str(r["pwc_value"])) for r in wh_rows)
        total_pwc_qty = sum(Decimal(str(r["pwc_qty"])) for r in wh_rows)
        total_movement_qty = sum(Decimal(str(r["movement_qty"])) for r in wh_rows)

        report["warehouse_summary"] = wh_rows
        report["summary"]["total_gl_value"] = float(total_gl_value)
        report["summary"]["overall_value_diff"] = float(total_pwc_value - total_gl_value)
        report["summary"]["all_matched_qty"] = all(r["matched_qty"] for r in wh_rows)
        report["summary"]["all_matched_value"] = all(r["matched_value"] for r in wh_rows)
        return report
