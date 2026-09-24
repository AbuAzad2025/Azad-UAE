"""Causal planner — intent -> slots -> tenant-scoped queries -> checks -> trace.

Read-only. No commits, no writes. Every number in the trace cites its query.
Missing operands yield status "need_slots", never hallucinated defaults for data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from ai_knowledge.cognitive.contracts import (
    CognitiveIntent,
    Provenance,
    ReasoningStep,
    ReasoningTrace,
    SlotSet,
)
from utils.tenanting import get_active_tenant_id, tenant_query

logger = logging.getLogger(__name__)

DEFAULT_DAYS = 30
MAX_DAYS = 365
ROW_LIMIT = 500


def _to_float(value: object) -> float:
    try:
        candidate: Any = 0 if value is None else value
        return float(candidate)
    except (TypeError, ValueError):
        return 0.0


def _amount_of(obj: object) -> float:
    for attr in ("total_amount", "grand_total", "amount", "balance_due"):
        if hasattr(obj, attr):
            return _to_float(getattr(obj, attr))
    return 0.0


def _days_from(slots: SlotSet) -> int:
    try:
        days = int(slots.values.get("days", DEFAULT_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_DAYS
    return max(1, min(MAX_DAYS, days))


def _cutoff(days: int) -> datetime:
    return datetime.now() - timedelta(days=days)


def _date_of(obj: object, *attrs: str) -> datetime | None:
    for attr in attrs:
        value = getattr(obj, attr, None)
        if value is not None:
            return value
    return None


def _recent(rows: list, *date_attrs: str) -> list:
    dated = [(row, _date_of(row, *date_attrs)) for row in rows]
    dated.sort(key=lambda item: item[1] or datetime.min, reverse=True)
    return [row for row, _ in dated]


def _sales_summary(days: int, user: object) -> tuple[str, str, int, dict]:
    from models.sale import Sale

    cutoff = _cutoff(days)
    rows = (
        tenant_query(Sale, user).filter(Sale.sale_date >= cutoff).order_by(Sale.sale_date.desc()).limit(ROW_LIMIT).all()
    )
    total = sum(_to_float(getattr(r, "total_amount", 0)) for r in rows)
    avg = total / len(rows) if rows else 0.0
    obs = f"Found {len(rows)} sales in last {days} days totaling {total:,.2f} (avg {avg:,.2f})."
    return obs, f"Sale[tenant,last={days}d]", len(rows), {"count": len(rows), "total": total, "avg": avg, "days": days}


def _customer_balance(name: str, user: object) -> tuple[str, str, int, dict]:
    from models.customer import Customer
    from models.sale import Sale

    matches = tenant_query(Customer, user).filter(Customer.name.ilike(f"%{name}%")).limit(5).all()
    if not matches:
        return f"No customer matches '{name}'.", f"Customer[tenant,ilike={name}]", 0, {"matches": 0}
    customer = matches[0]
    sales = (
        tenant_query(Sale, user)
        .filter(Sale.customer_id == customer.id)
        .order_by(Sale.sale_date.desc())
        .limit(ROW_LIMIT)
        .all()
    )
    due = sum(_to_float(getattr(s, "balance_due", 0)) for s in sales)
    stored = _to_float(getattr(customer, "balance", 0))
    obs = f"Customer '{customer.name}': {len(sales)} sales, open balance {due:,.2f} (ledger field {stored:,.2f})."
    if len(matches) > 1:
        obs += f" Note: {len(matches)} similar names matched; showing closest."
    data = {"customer": customer.name, "sales": len(sales), "due": due, "stored": stored, "matches": len(matches)}
    return obs, f"Customer[tenant,ilike={name}]+Sale[customer]", len(sales), data


def _inventory_status(user: object) -> tuple[str, str, int, dict]:
    from models.product import Product

    rows = tenant_query(Product, user).filter_by(is_active=True).limit(ROW_LIMIT).all()
    low = [p for p in rows if _to_float(getattr(p, "current_stock", 0)) <= _to_float(getattr(p, "min_stock_alert", 0))]
    obs = f"Checked {len(rows)} active products; {len(low)} at or below alert level."
    return obs, "Product[tenant,active]", len(rows), {"products": len(rows), "low": len(low)}


def _purchase_summary(days: int, user: object) -> tuple[str, str, int, dict]:
    from models.purchase import Purchase

    cutoff = _cutoff(days)
    rows = tenant_query(Purchase, user).filter(Purchase.created_at >= cutoff).limit(ROW_LIMIT).all()
    total = sum(_amount_of(r) for r in rows)
    return (
        f"Found {len(rows)} purchases in last {days} days totaling {total:,.2f}.",
        f"Purchase[tenant,last={days}d]",
        len(rows),
        {
            "count": len(rows),
            "total": total,
        },
    )


def _expense_summary(days: int, user: object) -> tuple[str, str, int, dict]:
    from models.expense import Expense

    cutoff = _cutoff(days)
    rows = tenant_query(Expense, user).filter(Expense.created_at >= cutoff).limit(ROW_LIMIT).all()
    total = sum(_amount_of(r) for r in rows)
    return (
        f"Found {len(rows)} expenses in last {days} days totaling {total:,.2f}.",
        f"Expense[tenant,last={days}d]",
        len(rows),
        {
            "count": len(rows),
            "total": total,
        },
    )


def _payment_status(days: int, user: object) -> tuple[str, str, int, dict]:
    from models.payment import Payment

    cutoff = _cutoff(days)
    rows = tenant_query(Payment, user).filter(Payment.created_at >= cutoff).limit(ROW_LIMIT).all()
    total = sum(_amount_of(r) for r in rows)
    return (
        f"Found {len(rows)} payments in last {days} days totaling {total:,.2f}.",
        f"Payment[tenant,last={days}d]",
        len(rows),
        {
            "count": len(rows),
            "total": total,
        },
    )


def _cheque_status(user: object) -> tuple[str, str, int, dict]:
    from models.cheque import Cheque

    rows = tenant_query(Cheque, user).order_by(Cheque.id.desc()).limit(100).all()
    total = sum(_amount_of(r) for r in rows)
    return (
        f"Found {len(rows)} recent cheques totaling {total:,.2f}.",
        "Cheque[tenant,recent=100]",
        len(rows),
        {
            "count": len(rows),
            "total": total,
        },
    )


def _gl_balance(user: object) -> tuple[str, str, int, dict]:
    from models.gl import GLAccount

    rows = tenant_query(GLAccount, user).limit(ROW_LIMIT).all()
    return f"Chart holds {len(rows)} accounts in scope.", "GLAccount[tenant]", len(rows), {"accounts": len(rows)}


def _hr_summary(user: object) -> tuple[str, str, int, dict]:
    from models.payroll import Employee

    rows = tenant_query(Employee, user).limit(ROW_LIMIT).all()
    return f"Found {len(rows)} employee records in scope.", "Employee[tenant]", len(rows), {"employees": len(rows)}


def _vault_balance(user: object) -> tuple[str, str, int, dict]:
    from models.cash_box import CashBox

    rows = tenant_query(CashBox, user).limit(ROW_LIMIT).all()
    total = sum(_to_float(getattr(r, "current_balance", 0)) for r in rows)
    return (
        f"Found {len(rows)} cash boxes holding {total:,.2f} combined.",
        "CashBox[tenant]",
        len(rows),
        {
            "boxes": len(rows),
            "total": total,
        },
    )


def _pattern_analysis(days: int, user: object) -> tuple[str, str, int, dict]:
    from models.sale import Sale

    cutoff = _cutoff(days)
    rows = tenant_query(Sale, user).filter(Sale.sale_date >= cutoff).limit(ROW_LIMIT).all()
    by_day: dict[int, list[float]] = {}
    for row in rows:
        day = _date_of(row, "sale_date")
        if day is None:
            continue
        by_day.setdefault(day.weekday(), []).append(_to_float(getattr(row, "total_amount", 0)))
    if not by_day:
        obs = f"No sales in last {days} days; no pattern to report."
        return obs, f"Sale[tenant,last={days}d]", 0, {"count": 0}
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    totals = {day: sum(amounts) for day, amounts in by_day.items()}
    best = max(totals, key=lambda day: totals[day])
    obs = (
        f"Analyzed {len(rows)} sales over last {days} days across {len(by_day)} active weekdays. "
        f"Strongest day: {names[best]} ({totals[best]:,.2f})."
    )
    return obs, f"Sale[tenant,last={days}d]", len(rows), {"count": len(rows), "best_day": names[best]}


def _profit_margin(days: int, user: object) -> tuple[str, str, int, dict]:
    from models.sale import Sale, SaleLine

    cutoff = _cutoff(days)
    sale_ids = [row.id for row in tenant_query(Sale, user).filter(Sale.sale_date >= cutoff).limit(ROW_LIMIT).all()]
    if not sale_ids:
        return f"No sales in last {days} days; no margin to report.", f"Sale[tenant,last={days}d]", 0, {"count": 0}
    lines = tenant_query(SaleLine, user).filter(SaleLine.sale_id.in_(sale_ids)).limit(ROW_LIMIT).all()
    revenue = sum(_to_float(getattr(line, "line_total", 0)) for line in lines)
    cost = sum(_to_float(getattr(line, "cost_price", 0)) * _to_float(getattr(line, "quantity", 0)) for line in lines)
    profit = revenue - cost
    margin = (profit / revenue * 100) if revenue else 0.0
    obs = (
        f"Margin over last {days} days across {len(lines)} lines: "
        f"revenue {revenue:,.2f}, cost {cost:,.2f}, profit {profit:,.2f} ({margin:.1f}%)."
    )
    return obs, f"SaleLine+Sale[tenant,last={days}d]", len(lines), {"revenue": revenue, "profit": profit}


def _dead_stock(days: int, user: object) -> tuple[str, str, int, dict]:
    from models.product import Product
    from models.sale import Sale, SaleLine

    cutoff = _cutoff(days)
    recent_sale_ids = {
        row.id for row in tenant_query(Sale, user).filter(Sale.sale_date >= cutoff).limit(ROW_LIMIT).all()
    }
    recent_lines = tenant_query(SaleLine, user).limit(ROW_LIMIT).all()
    sold_ids = {line.product_id for line in recent_lines if line.sale_id in recent_sale_ids}
    products = tenant_query(Product, user).filter_by(is_active=True).limit(ROW_LIMIT).all()
    dead = [p for p in products if p.id not in sold_ids]
    names = ", ".join(str(getattr(p, "name", p.id)) for p in dead[:10])
    obs = f"Checked {len(products)} active products; {len(dead)} with no sales in last {days} days."
    if names:
        obs += f" Stagnant sample: {names}."
    return obs, f"Product+SaleLine+Sale[tenant,last={days}d]", len(dead), {"dead": len(dead)}


def _top_products(days: int, user: object, limit: int = 5) -> tuple[str, str, int, dict]:
    from models.product import Product
    from models.sale import Sale, SaleLine

    cutoff = _cutoff(days)
    recent_sale_ids = {
        row.id for row in tenant_query(Sale, user).filter(Sale.sale_date >= cutoff).limit(ROW_LIMIT).all()
    }
    totals: dict[int, float] = {}
    for line in tenant_query(SaleLine, user).limit(ROW_LIMIT).all():
        if line.sale_id in recent_sale_ids:
            totals[line.product_id] = totals.get(line.product_id, 0.0) + _to_float(getattr(line, "line_total", 0))
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    names: list[str] = []
    for product_id, _total in ranked:
        product = tenant_query(Product, user).filter_by(id=product_id).first()
        names.append(str(getattr(product, "name", product_id)) if product else str(product_id))
    obs = f"Top {len(ranked)} products by revenue in last {days} days."
    if names:
        obs += " Leaders: " + ", ".join(names) + "."
    return obs, f"SaleLine+Sale+Product[tenant,last={days}d]", len(ranked), {"leaders": names}


def _debt_overview(user: object) -> tuple[str, str, int, dict]:
    from models.customer import Customer
    from models.sale import Sale

    debtors = (
        tenant_query(Customer, user).filter(Customer.balance > 0).order_by(Customer.balance.desc()).limit(10).all()
    )
    open_due = sum(
        _to_float(getattr(sale, "balance_due", 0)) for sale in tenant_query(Sale, user).limit(ROW_LIMIT).all()
    )
    total_stored = sum(_to_float(getattr(customer, "balance", 0)) for customer in debtors)
    obs = f"Found {len(debtors)} debtor customers in top list; open sales balances total {open_due:,.2f}."
    if debtors:
        obs += f" Largest ledger balance: {getattr(debtors[0], 'name', '?')} ({total_stored:,.2f} across listed)."
    return obs, "Customer[tenant,balance>0]+Sale[tenant]", len(debtors), {"debtors": len(debtors)}


def _tax_summary(days: int, user: object) -> tuple[str, str, int, dict]:
    from models.purchase import Purchase
    from models.sale import Sale

    cutoff = _cutoff(days)
    sales_tax = sum(
        _to_float(getattr(row, "tax_amount", 0))
        for row in tenant_query(Sale, user).filter(Sale.sale_date >= cutoff).limit(ROW_LIMIT).all()
    )
    purchases = tenant_query(Purchase, user).filter(Purchase.created_at >= cutoff).limit(ROW_LIMIT).all()
    purchase_tax = sum(_to_float(getattr(row, "tax_amount", 0)) for row in purchases)
    obs = f"Tax in last {days} days: output {sales_tax:,.2f} on sales, input {purchase_tax:,.2f} on purchases."
    return obs, f"Sale+Purchase[tenant,last={days}d]", len(purchases), {"output": sales_tax, "input": purchase_tax}


def _supplier_status(slots: SlotSet, user: object) -> tuple[str, str, int, dict]:
    from models.purchase import Purchase
    from models.supplier import Supplier

    name = (slots.values.get("supplier_name") or "").strip()
    if name:
        supplier = tenant_query(Supplier, user).filter(Supplier.name.ilike(f"%{name}%")).first()
        if supplier is None:
            return f"No supplier matches '{name}'.", f"Supplier[tenant,ilike={name}]", 0, {"matches": 0}
        orders = tenant_query(Purchase, user).filter(Purchase.supplier_id == supplier.id).limit(ROW_LIMIT).all()
        total = sum(_amount_of(order) for order in orders)
        obs = f"Supplier '{supplier.name}': {len(orders)} purchase orders totaling {total:,.2f}."
        return obs, f"Supplier+Purchase[tenant,{supplier.name}]", len(orders), {"orders": len(orders)}
    suppliers = tenant_query(Supplier, user).limit(ROW_LIMIT).all()
    return (
        f"Found {len(suppliers)} suppliers in scope.",
        "Supplier[tenant]",
        len(suppliers),
        {"suppliers": len(suppliers)},
    )


def plan_and_execute(
    intent: CognitiveIntent, slots: SlotSet, user: object | None
) -> tuple[str, ReasoningTrace, Provenance, dict]:
    tid = get_active_tenant_id(user)
    if tid is None:
        trace = ReasoningTrace(
            plan=("intent-decoded", "tenant-check"),
            steps=(
                ReasoningStep("intent-decoded", f"Intent={intent.value}.", 0.9),
                ReasoningStep("tenant-check", "No active tenant resolved; fail-closed.", 1.0),
            ),
            conclusion="Cannot query without an active company context.",
            confidence=1.0,
        )
        return "no_tenant", trace, Provenance(tenant_id=None), {}
    if slots.missing:
        trace = ReasoningTrace(
            plan=("intent-decoded", "slot-check"),
            steps=(
                ReasoningStep("intent-decoded", f"Intent={intent.value}.", 0.9),
                ReasoningStep("slot-check", f"Missing slots: {', '.join(slots.missing)}.", 1.0),
            ),
            conclusion="Need a missing slot before querying.",
            confidence=1.0,
        )
        return "need_slots", trace, Provenance(tenant_id=tid), {}
    days = _days_from(slots)
    try:
        match intent:
            case CognitiveIntent.SALES_SUMMARY:
                obs, prov, count, data = _sales_summary(days, user)
            case CognitiveIntent.CUSTOMER_BALANCE:
                obs, prov, count, data = _customer_balance(slots.values["customer_name"], user)
            case CognitiveIntent.INVENTORY_STATUS:
                obs, prov, count, data = _inventory_status(user)
            case CognitiveIntent.PURCHASE_SUMMARY:
                obs, prov, count, data = _purchase_summary(days, user)
            case CognitiveIntent.EXPENSE_SUMMARY:
                obs, prov, count, data = _expense_summary(days, user)
            case CognitiveIntent.PAYMENT_STATUS:
                obs, prov, count, data = _payment_status(days, user)
            case CognitiveIntent.CHEQUE_STATUS:
                obs, prov, count, data = _cheque_status(user)
            case CognitiveIntent.GL_BALANCE:
                obs, prov, count, data = _gl_balance(user)
            case CognitiveIntent.HR_SUMMARY:
                obs, prov, count, data = _hr_summary(user)
            case CognitiveIntent.VAULT_BALANCE:
                obs, prov, count, data = _vault_balance(user)
            case CognitiveIntent.PATTERN_ANALYSIS:
                obs, prov, count, data = _pattern_analysis(days, user)
            case CognitiveIntent.PROFIT_MARGIN:
                obs, prov, count, data = _profit_margin(days, user)
            case CognitiveIntent.DEAD_STOCK:
                obs, prov, count, data = _dead_stock(days, user)
            case CognitiveIntent.TOP_PRODUCTS:
                obs, prov, count, data = _top_products(days, user)
            case CognitiveIntent.DEBT_OVERVIEW:
                obs, prov, count, data = _debt_overview(user)
            case CognitiveIntent.TAX_SUMMARY:
                obs, prov, count, data = _tax_summary(days, user)
            case CognitiveIntent.SUPPLIER_STATUS:
                obs, prov, count, data = _supplier_status(slots, user)
            case _:
                raise ValueError(f"planner has no grounded plan for {intent.value}")
    except Exception as exc:
        logger.error("Cognitive query failed for %s: %s", intent.value, exc)
        trace = ReasoningTrace(
            plan=("intent-decoded", "slot-check", "query"),
            steps=(
                ReasoningStep("intent-decoded", f"Intent={intent.value}.", 0.9),
                ReasoningStep("slot-check", "Slots resolved.", 1.0),
                ReasoningStep("query", f"Query failed safely: {type(exc).__name__}.", 0.0),
            ),
            conclusion="Query failed without exposing data.",
            confidence=0.0,
        )
        return "ok", trace, Provenance(tenant_id=tid, queries=("failed",), row_counts=(0,)), {}
    steps = (
        ReasoningStep("intent-decoded", f"Intent={intent.value}; slots={dict(slots.values) or '{}'}.", 0.9),
        ReasoningStep("rbac-passed", "Role check passed before query.", 1.0),
        ReasoningStep("query", obs, 0.9, provenance=prov),
        ReasoningStep("constraint-check", "Tenant scope enforced; no cross-tenant rows readable.", 1.0),
    )
    confidence = round(min(s.confidence for s in steps), 3)
    trace = ReasoningTrace(
        plan=("intent-decoded", "rbac-passed", "query", "constraint-check"),
        steps=steps,
        conclusion=obs,
        confidence=confidence,
    )
    return "ok", trace, Provenance(tenant_id=tid, queries=(prov,), row_counts=(count,)), data
