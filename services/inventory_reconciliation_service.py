"""Inventory reconciliation: PWC vs GL inventory account vs stock movements.

Compares three sources:
1. ProductWarehouseCost (PWC) — operational stock valuation
2. GLJournalLine for account 1140 (inventory asset) — ledger balance
3. stock_movements — physical movement trail (quantity audit)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import func, text

from extensions import db
from models import (
    GLAccount,
    GLJournalEntry,
    GLJournalLine,
    Product,
    ProductWarehouseCost,
    Warehouse,
)
from services.gl_service import GL_ACCOUNTS
from utils.gl_tenant import scope_gl_accounts

# Tolerance for floating-point rounding in reconciliation
RECON_TOLERANCE = Decimal("0.01")


class InventoryReconciliationService:
    @staticmethod
    def _date_bound(value, *, end_of_day: bool):
        """Normalize date input from UI filters before comparing DateTime columns."""
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time.max if end_of_day else time.min)

        text_value = str(value).strip()
        if not text_value:
            return None

        try:
            if len(text_value) == 10:
                parsed_date = date.fromisoformat(text_value)
                return datetime.combine(parsed_date, time.max if end_of_day else time.min)
            return datetime.fromisoformat(text_value)
        except ValueError:
            return None

    @classmethod
    def _date_bounds(cls, date_from: str | None, date_to: str | None):
        return (
            cls._date_bound(date_from, end_of_day=False),
            cls._date_bound(date_to, end_of_day=True),
        )

    @staticmethod
    def _gl_inventory_balance(
        account_id: int,
        tenant_id: int | None,
        branch_id: int | None,
        warehouse_id: str | None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> Decimal:
        """Sum of (debit − credit) for the inventory account with optional filters.

        BUG FIX: previous version used ``for q in (debit_q, credit_q): q = q.filter(...)``
        which reassigned the *loop variable* without mutating debit_q/credit_q.
        Filters were silently ignored.  Now we apply filters directly to both queries.
        """
        date_start, date_end = InventoryReconciliationService._date_bounds(date_from, date_to)

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
        if date_start:
            debit_q = debit_q.filter(GLJournalEntry.entry_date >= date_start)
            credit_q = credit_q.filter(GLJournalEntry.entry_date >= date_start)
        if date_end:
            debit_q = debit_q.filter(GLJournalEntry.entry_date <= date_end)
            credit_q = credit_q.filter(GLJournalEntry.entry_date <= date_end)

        return Decimal(str(debit_q.scalar() or 0)) - Decimal(str(credit_q.scalar() or 0))

    @classmethod
    def _movement_net_qty(
        cls,
        tenant_id: int,
        product_id: int,
        warehouse_id: int,
        branch_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> Decimal:
        date_start, date_end = cls._date_bounds(date_from, date_to)
        sql = """
            SELECT COALESCE(SUM(quantity), 0)
            FROM stock_movements sm
            WHERE sm.tenant_id = :tid
              AND sm.product_id = :pid
              AND sm.warehouse_id = :wid
        """
        params: dict[str, Any] = {
            "tid": tenant_id,
            "pid": product_id,
            "wid": warehouse_id,
        }
        if branch_id is not None:
            sql += """
              AND EXISTS (
                  SELECT 1
                  FROM warehouses w
                  WHERE w.id = sm.warehouse_id
                    AND w.branch_id = :bid
              )
            """
            params["bid"] = branch_id
        if date_start:
            sql += " AND sm.created_at >= :df"
            params["df"] = date_start
        if date_end:
            sql += " AND sm.created_at <= :dt"
            params["dt"] = date_end
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
        if branch_id is not None:
            pwc_query = pwc_query.join(Warehouse, ProductWarehouseCost.warehouse_id == Warehouse.id).filter(
                Warehouse.branch_id == branch_id
            )
            if tenant_id is not None:
                pwc_query = pwc_query.filter(Warehouse.tenant_id == tenant_id)

        pwc_records = pwc_query.all()

        rows = []
        total_pwc_value = Decimal("0")
        total_pwc_qty = Decimal("0")
        total_movement_qty = Decimal("0")

        for pwc in pwc_records:
            product = db.session.get(Product, pwc.product_id)
            warehouse = db.session.get(Warehouse, pwc.warehouse_id)

            movement_qty = cls._movement_net_qty(
                pwc.tenant_id,
                pwc.product_id,
                pwc.warehouse_id,
                branch_id=branch_id,
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
                    "warehouse_name": (warehouse.name if warehouse else f"#{pwc.warehouse_id}"),
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

        warehouse_map: dict[str, dict[str, Any]] = defaultdict(
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
            if inventory_account:
                gl_value = cls._gl_inventory_balance(
                    inventory_account.id,
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    warehouse_id=wid,
                    date_from=date_from,
                    date_to=date_to,
                )

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
                    "tagged_gl_value": float(gl_value),
                    "unallocated_gl_value": 0.0,
                    "value_diff": float(value_diff),
                    "matched_qty": abs(qty_diff) <= RECON_TOLERANCE,
                    "matched_value": abs(value_diff) <= RECON_TOLERANCE,
                    "gl_untagged": False,
                }
            )

        tagged_gl_value = sum(Decimal(str(r["gl_value"])) for r in wh_rows)
        scope_gl_value = Decimal("0")
        if inventory_account:
            scope_gl_value = cls._gl_inventory_balance(
                inventory_account.id,
                tenant_id=tenant_id,
                branch_id=branch_id,
                warehouse_id=None,
                date_from=date_from,
                date_to=date_to,
            )
        unallocated_gl_value = scope_gl_value - tagged_gl_value

        # If the current report scope has a single warehouse, legacy untagged
        # GL can be displayed on that row while still marked as unallocated.
        if len(wh_rows) == 1 and warehouse_id is None and abs(unallocated_gl_value) > RECON_TOLERANCE:
            row = wh_rows[0]
            effective_gl = Decimal(str(row["gl_value"])) + unallocated_gl_value
            value_diff = Decimal(str(row["pwc_value"])) - effective_gl
            row["gl_value"] = float(effective_gl)
            row["unallocated_gl_value"] = float(unallocated_gl_value)
            row["value_diff"] = float(value_diff)
            row["gl_untagged"] = True
            row["matched_value"] = False

        # Overall totals from scoped ledger balance (no double-counting)
        total_gl_value = scope_gl_value
        total_pwc_value = sum(Decimal(str(r["pwc_value"])) for r in wh_rows)
        sum(Decimal(str(r["pwc_qty"])) for r in wh_rows)
        sum(Decimal(str(r["movement_qty"])) for r in wh_rows)
        overall_value_diff = total_pwc_value - total_gl_value
        has_unallocated_gl = abs(unallocated_gl_value) > RECON_TOLERANCE

        report["warehouse_summary"] = wh_rows
        report["summary"]["tagged_gl_value"] = float(tagged_gl_value)
        report["summary"]["unallocated_gl_value"] = float(unallocated_gl_value)
        report["summary"]["total_gl_value"] = float(total_gl_value)
        report["summary"]["overall_value_diff"] = float(overall_value_diff)
        report["summary"]["all_matched_qty"] = all(r["matched_qty"] for r in wh_rows)
        report["summary"]["all_matched_value"] = abs(overall_value_diff) <= RECON_TOLERANCE and not has_unallocated_gl
        report["summary"]["has_unallocated_gl"] = has_unallocated_gl
        report["summary"]["all_warehouse_values_matched"] = all(r["matched_value"] for r in wh_rows)
        report["summary"]["all_matched"] = (
            report["summary"]["all_matched_qty"] and report["summary"]["all_matched_value"]
        )
        return report
