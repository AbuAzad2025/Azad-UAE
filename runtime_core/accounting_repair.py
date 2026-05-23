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

    GLService.ensure_core_accounts()

    merchant = Customer.query.filter_by(customer_type="merchant").order_by(Customer.id.asc()).first()
    if not merchant:
        merchant = Customer(
            name="Default Merchant",
            name_ar="التاجر الافتراضي",
            customer_type="merchant",
            is_active=True,
        )
        db.session.add(merchant)
        db.session.flush()

    updated_products = 0
    products_without_merchant = Product.query.filter(Product.merchant_customer_id.is_(None)).all()
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

    inventory_account = GLAccount.query.filter_by(code="1140").first()
    equity_account = GLAccount.query.filter_by(code="3200").first()
    if not inventory_account or not equity_account:
        raise RuntimeError("الحسابات 1140 أو 3200 غير موجودة في شجرة الحسابات.")

    gl_inventory = sum(
        Decimal(str(line.debit or 0)) - Decimal(str(line.credit or 0))
        for line in GLJournalLine.query.filter(GLJournalLine.account_id == inventory_account.id).all()
    )
    estimated_inventory = sum(
        Decimal(str(product.current_stock or 0)) * Decimal(str(product.cost_price or 0))
        for product in Product.query.all()
    )
    inventory_diff = estimated_inventory - gl_inventory

    posted_inventory_adjustment = Decimal("0")
    if abs(inventory_diff) > Decimal("0.01"):
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

        GLService.post_entry(
            lines=lines,
            description="Initial inventory migration adjustment",
            reference_type="inventory_migration",
            reference_id=None,
            currency="AED",
            exchange_rate=1.0,
        )

    db.session.commit()

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
