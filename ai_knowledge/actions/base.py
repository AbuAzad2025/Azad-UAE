"""Shared seam for AI action packs (Master Directive expansion).

Every pack is an independent domain module (cheques / returns / quotations /
catalog) with its own handlers, command patterns, and help lines. This
module is the ONLY import seam between packs and the dispatcher core —
packs never import ``action_dispatcher`` privates directly, which keeps
each pack maintainable, traceable, and safe to evolve in isolation.

Rules every pack handler must follow:
- Resolve ``tenant_id`` via :func:`tenant_guard` first (fail-closed).
- Mutate exclusively through the validated service layer
  (``ChequeService`` / ``ReturnService`` / ``QuotationService`` /
  ``StockService`` / …) inside ``atomic_transaction``.
- Never touch balances, GL postings, or payment-vault rows directly.
- Funnel every error through :func:`pack_error` so failures are logged
  with the action name and request args (traceability).
"""

from __future__ import annotations

import logging
from typing import Any

# Top-level import is safe by design: the dispatcher instantiates its
# singleton with CORE actions only (packs register lazily on first use),
# so importing these names can never trigger a pack import cycle.
from ai_knowledge.action_dispatcher import (
    ActionResult,
    _audit,
    _escape_ilike,
    _log_ai_error,
    _tenant_guard,
)
from utils.db_safety import atomic_transaction

logger = logging.getLogger(__name__)

__all__ = [
    "ActionResult",
    "atomic_transaction",
    "tenant_guard",
    "audit",
    "pack_error",
    "escape_like",
    "resolve_customer",
    "resolve_product",
    "resolve_supplier",
    "resolve_warehouse",
    "actor",
]


def tenant_guard():
    """Return ``(tenant_id, None)`` or ``(None, ActionResult)`` when missing."""
    return _tenant_guard()


def audit(action: str, entity: str, entity_id: int | None = None, details: dict | None = None) -> None:
    """Central audit entry (delegates to the dispatcher core)."""
    _audit(action, entity, entity_id, details)


def pack_error(action: str, exc: Exception, args: dict | None = None) -> ActionResult:
    """Log a pack failure with action context and return a safe message."""
    _log_ai_error(f"{action}_error", str(exc), request_data=dict(args or {}))
    return ActionResult(False, f"خطأ في {action}: {str(exc)[:120]}")


def escape_like(term: str) -> str:
    """Escape SQL LIKE wildcards in user-provided search terms."""
    return _escape_ilike(term)


def actor():
    """Current request user or None (pack handlers decide auth requirements)."""
    try:
        from flask_login import current_user

        if getattr(current_user, "is_authenticated", False):
            return current_user
    except Exception as exc:
        logger.debug("Pack actor resolution skipped: %s", exc)
    return None


def resolve_customer(tenant_id: int, name: str):
    """First active tenant customer whose name contains ``name`` (or None)."""
    from models import Customer

    safe = _escape_ilike((name or "").strip())
    if not safe:
        return None
    return (
        Customer.query.filter(
            Customer.tenant_id == tenant_id,
            Customer.is_active,
            Customer.name.ilike(f"%{safe}%", escape="\\"),
        )
        .order_by(Customer.name)
        .first()
    )


def resolve_product(tenant_id: int, name: str):
    """First active tenant product whose name/SKU contains ``name`` (or None)."""
    from models import Product

    safe = _escape_ilike((name or "").strip())
    if not safe:
        return None
    return (
        Product.query.filter(
            Product.tenant_id == tenant_id,
            Product.is_active,
            (Product.name.ilike(f"%{safe}%", escape="\\")) | (Product.sku.ilike(f"%{safe}%", escape="\\")),
        )
        .order_by(Product.name)
        .first()
    )


def resolve_supplier(tenant_id: int, name: str):
    """First active tenant supplier whose name contains ``name`` (or None)."""
    from models import Supplier

    safe = _escape_ilike((name or "").strip())
    if not safe:
        return None
    return (
        Supplier.query.filter(
            Supplier.tenant_id == tenant_id,
            Supplier.is_active,
            Supplier.name.ilike(f"%{safe}%", escape="\\"),
        )
        .order_by(Supplier.name)
        .first()
    )


def resolve_warehouse(tenant_id: int, warehouse_id: int):
    """Active tenant warehouse by id (or None when missing/foreign)."""
    from models import Warehouse

    if not warehouse_id:
        return None
    warehouse = Warehouse.query.filter_by(id=int(warehouse_id), tenant_id=tenant_id, is_active=True).first()
    return warehouse


def result_message(ok: bool, text: str, data: Any = None, action_type: str = "") -> ActionResult:
    """Small constructor to keep pack handlers uniform."""
    return ActionResult(ok, text, data or {}, action_type)
