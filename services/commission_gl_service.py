"""Post partner commission GL entries for a sale."""

from __future__ import annotations

import logging
from decimal import Decimal

from flask_babel import gettext

from extensions import db
from models import PartnerCommissionEntry
from services.gl_posting import post_or_fail
from services.gl_service import GLService
from utils.gl_reference_types import GLRef

logger = logging.getLogger(__name__)


def _sync_partner_ledger_for_commissions(sale, entries) -> None:
    """Mirror sale commissions into the partner's own ledger.

    A product-level partner earns a commission through a Customer row
    (``PartnerCommissionEntry.partner_customer_id``). A company-level Partner
    is linked to that customer through ``Customer.partner_id``. The GL credit
    to the partner current account is only half the picture: without this
    mirror the partner's statement and ``current_balance`` never show the
    entitlement, so the two ledgers disagree.

    The sync is idempotent per ``(tenant, partner, sale)`` so re-running a
    posting cannot double-credit a partner.
    """
    from datetime import UTC, datetime
    from decimal import ROUND_HALF_UP

    from models import Partner, PartnerTransaction

    per_partner: dict[int, Decimal] = {}
    for entry in entries:
        customer = getattr(entry, "partner_customer", None)
        partner_id = getattr(customer, "partner_id", None) if customer is not None else None
        if not isinstance(partner_id, int):
            continue
        amount = Decimal(str(entry.commission_amount_aed or 0)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if amount == 0:
            continue
        per_partner[partner_id] = per_partner.get(partner_id, Decimal("0")) + amount

    for partner_id, amount in per_partner.items():
        existing = PartnerTransaction.query.filter_by(
            tenant_id=sale.tenant_id,
            partner_id=partner_id,
            reference_type="sale_commission",
            reference_id=sale.id,
        ).first()
        if existing is not None:
            continue
        partner = db.session.get(Partner, partner_id)
        if not partner or partner.tenant_id != sale.tenant_id:
            continue
        new_balance = Decimal(str(partner.current_balance or 0)) + amount
        sale_date = getattr(sale, "sale_date", None)
        if sale_date is not None and hasattr(sale_date, "date"):
            transaction_date = sale_date.date()
        else:
            transaction_date = sale_date or datetime.now(UTC).date()
        db.session.add(
            PartnerTransaction(
                tenant_id=sale.tenant_id,
                partner_id=partner_id,
                transaction_type="sale_commission",
                amount=amount,
                amount_base=amount,
                balance_after=new_balance,
                reference_number=sale.sale_number,
                reference_type="sale_commission",
                reference_id=sale.id,
                transaction_date=transaction_date,
                notes=gettext(f"عمولة مبيعات — {sale.sale_number}"),
            )
        )
        partner.current_balance = new_balance
        db.session.flush()


def post_sale_commissions(sale):
    entries = PartnerCommissionEntry.query.filter_by(sale_id=sale.id, tenant_id=sale.tenant_id).all()
    if not entries:
        return None

    total = sum(Decimal(str(e.commission_amount_aed or 0)) for e in entries)
    if total <= Decimal("0"):
        return None

    # Dynamic currency: use sale's exchange rate and base currency
    exchange_rate = Decimal(str(sale.exchange_rate)) if sale.exchange_rate else Decimal("1")
    base_currency = getattr(sale, "currency", "AED")
    try:
        from utils.currency_utils import resolve_tenant_base_currency

        base_currency = resolve_tenant_base_currency(tenant_id=sale.tenant_id) or base_currency
    except Exception:
        logger.warning(
            "Failed to resolve tenant base currency for commission GL, using default",
            exc_info=True,
        )

    GLService.ensure_core_accounts(tenant_id=getattr(sale, "tenant_id", None))
    tenant_id = getattr(sale, "tenant_id", None)
    branch_id = sale.branch_id
    commission_expense_account = GLService.get_account_code_for_concept(
        "COMMISSION_EXPENSE", tenant_id=tenant_id, branch_id=branch_id
    )
    partner_account = GLService.get_account_code_for_concept(
        "PARTNER_CURRENT_ACCOUNT", tenant_id=tenant_id, branch_id=branch_id
    )
    result = post_or_fail(
        [
            {
                "account": commission_expense_account,
                "concept_code": "COMMISSION_EXPENSE",
                "debit": total,
                "description": gettext(f"عمولات شركاء — {sale.sale_number}"),
            },
            {
                "account": partner_account,
                "concept_code": "PARTNER_CURRENT_ACCOUNT",
                "credit": total,
                "description": gettext(f"جاري شركاء — {sale.sale_number}"),
            },
        ],
        description=f"Partner commissions {sale.sale_number}",
        reference_type=GLRef.PARTNER_COMMISSION,
        reference_id=sale.id,
        exchange_rate=exchange_rate,
        branch_id=branch_id,
        tenant_id=getattr(sale, "tenant_id", None),
    )
    # The GL is posted first: a failed posting must not leave a partner ledger
    # entry behind. Both live in the caller's atomic transaction.
    _sync_partner_ledger_for_commissions(sale, entries)
    return result
