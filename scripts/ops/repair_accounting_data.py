"""
Opt-in accounting data repair. NOT part of application startup.

This lives in ``scripts/ops/`` because it is a deliberate maintenance command, not
boot logic. ``app/bootstrap.py`` is the single self-healing entry point; this
repair is deliberately excluded from it, for three reasons that are worth keeping
written down:

1. Rule 4 posts a real GL journal entry. Posting accounting entries on every
   ``flask run`` is not self-healing, it is self-posting.
2. Its guard compares ``sum(Product.current_stock * cost_price)`` against the
   balance of account 1140. Those two legitimately disagree - stock transfers,
   write-offs, PWC valuation and FX revaluation all move one without the other -
   so the "difference" it posts is not a real invariant and would drift.
3. Rules 1 and 2 fabricate business data. They create a synthetic "Default
   Merchant" customer and attach every product that lacks a merchant to it. A
   product with no merchant partner is legitimately NULL: ``services/
   reports_query_service.py`` filters ``merchant_customer_id.isnot(None)`` to find
   merchant-share products, and ``routes/products.py`` sets it from an explicit
   form field. Auto-assigning a placeholder would make every product look like a
   revenue-share arrangement.

Historically ``utils/system_init.py`` called this at startup; that wiring is gone
and the module used to be ``app/runtime/accounting_repair.py``, where its location
and a false docstring made it read like a live boot path. It is retained here
because the backfill rules are still the correct answer for a database carrying
legacy data - they just must be run by a human who has decided that is the case.

Run it deliberately::

    python -m scripts.ops.repair_accounting_data --tenant-id 1
    python -m scripts.ops.repair_accounting_data --list-tenants

Do not wire this into ``create_app``. If a rule here ever needs to run for every
new tenant, it belongs in tenant provisioning; if it is a one-off correction of
historical rows, it belongs in an Alembic data migration - not in either case on
the boot path.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from flask import current_app

from extensions import db
from utils.db_safety import atomic_transaction


def repair_accounting_data(tenant_id: int | None = None):
    """
    Idempotent accounting data repair, scoped to one tenant.

    - Ensure a valid default merchant customer exists.
    - Link products missing `merchant_customer_id`.
    - Backfill legacy cheque GL entries missing reference_type/reference_id.
    - Post an opening inventory migration adjustment only when a real diff exists.

    NOT safe to run unattended on every startup - see the module docstring. Pass
    ``tenant_id`` explicitly; with no argument it falls back to the active tenant
    context and then to the lowest-id active tenant, which is only appropriate
    for a single-tenant database.
    """
    from models import Cheque, Customer, Product
    from models.gl import GLJournalEntry, GLJournalLine
    from services import gl_helpers
    from services.gl_service import GLService

    target_tenant_id = tenant_id
    if target_tenant_id is None:
        from utils.tenanting import get_active_tenant_id

        target_tenant_id = get_active_tenant_id()
    if target_tenant_id is None:
        from models import Tenant

        default_tenant = Tenant.query.filter_by(is_active=True).order_by(Tenant.id.asc()).first()
        target_tenant_id = default_tenant.id if default_tenant else None

    with atomic_transaction("accounting_repair"):
        GLService.ensure_core_accounts(tenant_id=target_tenant_id)

    if target_tenant_id is None:
        raise RuntimeError("inventory migration requires an active tenant context")

    with atomic_transaction("accounting_repair_data"):
        merchant = (
            Customer.query.filter_by(
                customer_type="merchant",
                tenant_id=target_tenant_id,
            )
            .order_by(Customer.id.asc())
            .first()
        )
        if not merchant:
            merchant = Customer(
                tenant_id=target_tenant_id,
                name="Default Merchant",
                name_ar="التاجر الافتراضي",
                customer_type="merchant",
                is_active=True,
            )
            db.session.add(merchant)
            db.session.flush()

        updated_products = 0
        products_without_merchant = Product.query.filter(
            Product.merchant_customer_id.is_(None),
            Product.tenant_id == target_tenant_id,
        ).all()
        for product in products_without_merchant:
            product.merchant_customer_id = merchant.id
            updated_products += 1

        backfilled_entries = 0
        legacy_entries = GLJournalEntry.query.filter(
            GLJournalEntry.reference_type.is_(None),
            GLJournalEntry.tenant_id == int(target_tenant_id),
        ).all()
        for entry in legacy_entries:
            description = entry.description or ""
            match = re.search(r"رقم\s+([A-Za-z0-9\-]+)", description)
            if not match:
                continue

            cheque_number = match.group(1).strip()
            cheque = Cheque.query.filter(
                (Cheque.cheque_number == cheque_number) | (Cheque.cheque_bank_number == cheque_number),
                Cheque.tenant_id == int(target_tenant_id),
            ).first()
            if not cheque:
                continue

            if "استلام شيك وارد" in description:
                entry.reference_type = "cheque_receive"
            elif "إصدار شيك صادر" in description:
                entry.reference_type = "cheque_issue"
            elif "ارتداد شيك" in description:
                entry.reference_type = "cheque_bounce"
            elif "إلغاء شيك" in description:
                entry.reference_type = "cheque_cancel"
            else:
                continue

            entry.reference_id = cheque.id
            backfilled_entries += 1

        inventory_account = gl_helpers.get_account("1140", target_tenant_id)
        equity_account = gl_helpers.get_account("3200", target_tenant_id)
        if not inventory_account or not equity_account:
            raise RuntimeError(f"الحسابات 1140 أو 3200 غير موجودة لـ tenant_id={target_tenant_id}.")

        gl_inventory = sum(
            (
                Decimal(str(line.debit or 0)) - Decimal(str(line.credit or 0))
                for line in GLJournalLine.query.filter(
                    GLJournalLine.account_id == inventory_account.id,
                    GLJournalLine.tenant_id == int(target_tenant_id),
                ).all()
            ),
            Decimal("0"),
        )
        from utils.tenant_orm import tenant_query

        estimated_inventory = sum(
            (
                Decimal(str(product.current_stock or 0)) * Decimal(str(product.cost_price or 0))
                for product in tenant_query(Product).all()
            ),
            Decimal("0"),
        )
        inventory_diff = estimated_inventory - gl_inventory

        existing_migration = GLJournalEntry.query.filter_by(
            reference_type="InventoryMigration",
            tenant_id=int(target_tenant_id),
        ).first()
        posted_inventory_adjustment: Decimal
        if existing_migration:
            posted_inventory_adjustment = Decimal("0")
        elif abs(inventory_diff) > Decimal("0.01"):
            posted_inventory_adjustment = inventory_diff
            lines: list[dict[str, Any]]
            if inventory_diff > 0:
                lines = [
                    {
                        "account": "1140",
                        "concept_code": "INVENTORY_ASSET",
                        "debit": inventory_diff,
                        "description": "Opening inventory migration adjustment",
                    },
                    {
                        "account": "3200",
                        "credit": inventory_diff,
                        "description": "Opening inventory offset to retained earnings",
                    },
                ]
            else:
                diff_abs = abs(inventory_diff)
                lines = [
                    {
                        "account": "3200",
                        "debit": diff_abs,
                        "description": "Reverse opening inventory migration adjustment",
                    },
                    {
                        "account": "1140",
                        "concept_code": "INVENTORY_ASSET",
                        "credit": diff_abs,
                        "description": "Reverse opening inventory offset",
                    },
                ]

            from models import Branch

            branch = (
                Branch.query.filter_by(tenant_id=int(target_tenant_id), is_main=True).first()
                or Branch.query.filter_by(tenant_id=int(target_tenant_id)).order_by(Branch.id.asc()).first()
            )
            GLService.post_entry(
                lines=lines,
                description="Initial inventory migration adjustment",
                reference_type="InventoryMigration",
                currency="AED",
                branch_id=branch.id if branch else None,
                tenant_id=int(target_tenant_id),
            )
        else:
            posted_inventory_adjustment = Decimal("0")

    current_app.logger.info(
        "AccountingRepair: merchant_id=%s products_linked=%s legacy_cheque_refs=%s inventory_adjustment=%s",
        merchant.id,
        updated_products,
        backfilled_entries,
        posted_inventory_adjustment,
    )

    return {
        "merchant_id": merchant.id,
        "products_linked": updated_products,
        "legacy_cheque_refs": backfilled_entries,
        "inventory_adjustment": posted_inventory_adjustment,
    }


def _main() -> int:
    """Run the repair for one explicitly named tenant."""
    import argparse
    import os
    import sys

    from app.factory import create_app

    parser = argparse.ArgumentParser(
        description="Opt-in accounting data repair (NOT run at startup).",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--tenant-id",
        type=int,
        help="tenant to repair",
    )
    group.add_argument(
        "--list-tenants",
        action="store_true",
        help="list active tenants and exit without changing anything",
    )
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL is not set; refusing to guess a database.", file=sys.stderr)
        return 2

    app = create_app()
    with app.app_context():
        if args.list_tenants:
            from models import Tenant

            for tenant in Tenant.query.filter_by(is_active=True).order_by(Tenant.id.asc()).all():
                print(f"  {tenant.id}  {tenant.name}  ({tenant.slug})")
            return 0

        result = repair_accounting_data(tenant_id=args.tenant_id)
        print(f"merchant_id          = {result['merchant_id']}")
        print(f"products_linked      = {result['products_linked']}")
        print(f"legacy_cheque_refs   = {result['legacy_cheque_refs']}")
        print(f"inventory_adjustment = {result['inventory_adjustment']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
