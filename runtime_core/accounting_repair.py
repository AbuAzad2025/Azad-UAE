from __future__ import annotations

"""
RUNTIME CORE FILE.

This module is called from `utils/system_init.py` during normal application startup.
Do not delete or move it without updating startup wiring.
"""

import re
from decimal import Decimal

from flask import current_app

from extensions import db


def repair_accounting_data():
    """
    Idempotent accounting data repair.

    Safe to run on startup:
    - Ensure a valid default merchant customer exists.
    - Link products missing `merchant_customer_id`.
    - Backfill legacy cheque GL entries missing reference_type/reference_id.
    - Post an opening inventory migration adjustment only when a real diff exists.
    """
    from models import Cheque, Customer, Product
    from models.gl import GLAccount, GLJournalEntry, GLJournalLine
    from services.gl_service import GLService
    from services import gl_helpers
    from utils.tenanting import get_active_tenant_id

    tenant_id = get_active_tenant_id()
    if tenant_id is None:
        from models import Tenant
        default_tenant = Tenant.query.filter_by(is_active=True).order_by(Tenant.id.asc()).first()
        tenant_id = default_tenant.id if default_tenant else None

    GLService.ensure_core_accounts(tenant_id=tenant_id)

    merchant = Customer.query.filter_by(customer_type="merchant", tenant_id=tenant_id).order_by(Customer.id.asc()).first()
    if not merchant:
        merchant = Customer(
            tenant_id=tenant_id,
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
        Product.tenant_id == tenant_id,
    ).all()
    for product in products_without_merchant:
        product.merchant_customer_id = merchant.id
        updated_products += 1

    backfilled_entries = 0
    legacy_entries = GLJournalEntry.query.filter(GLJournalEntry.reference_type.is_(None)).all()
    for entry in legacy_entries:
        description = entry.description or ""
        match = re.search(r"رقم\s+([A-Za-z0-9\-]+)", description)
        if not match:
            continue

        cheque_number = match.group(1).strip()
        cheque = Cheque.query.filter(
            (Cheque.cheque_number == cheque_number) | (Cheque.cheque_bank_number == cheque_number)
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

    if tenant_id is None:
        raise RuntimeError("inventory migration requires an active tenant context")

    inventory_account = gl_helpers.get_account("1140", tenant_id)
    equity_account = gl_helpers.get_account("3200", tenant_id)
    if not inventory_account or not equity_account:
        raise RuntimeError(f"الحسابات 1140 أو 3200 غير موجودة لـ tenant_id={tenant_id}.")

    gl_inventory = sum(
        Decimal(str(line.debit or 0)) - Decimal(str(line.credit or 0))
        for line in GLJournalLine.query.filter(GLJournalLine.account_id == inventory_account.id).all()
    )
    from utils.tenant_orm import tenant_query

    estimated_inventory = sum(
        Decimal(str(product.current_stock or 0)) * Decimal(str(product.cost_price or 0))
        for product in tenant_query(Product).all()
    )
    inventory_diff = estimated_inventory - gl_inventory

    posted_inventory_adjustment = Decimal("0")
    existing_migration = GLJournalEntry.query.filter_by(
        reference_type="InventoryMigration",
        tenant_id=int(tenant_id),
    ).first()
    if existing_migration:
        posted_inventory_adjustment = Decimal("0")
    elif abs(inventory_diff) > Decimal("0.01"):
        posted_inventory_adjustment = inventory_diff
        if inventory_diff > 0:
            lines = [
                {
                    "account": "1140",
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
                    "credit": diff_abs,
                    "description": "Reverse opening inventory offset",
                },
            ]

        from models import Branch

        branch = (
            Branch.query.filter_by(tenant_id=int(tenant_id), is_main=True).first()
            or Branch.query.filter_by(tenant_id=int(tenant_id)).order_by(Branch.id.asc()).first()
        )
        GLService.post_entry(
            lines=lines,
            description="Initial inventory migration adjustment",
            reference_type="InventoryMigration",
            reference_id=None,
            currency="AED",
            exchange_rate=1.0,
            branch_id=branch.id if branch else None,
            tenant_id=int(tenant_id),
        )
    else:
        posted_inventory_adjustment = Decimal("0")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

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
