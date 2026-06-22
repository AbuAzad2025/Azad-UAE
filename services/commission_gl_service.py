"""Post partner commission GL entries for a sale."""
from __future__ import annotations

from decimal import Decimal

from extensions import db
from models import PartnerCommissionEntry
from services.gl_posting import post_or_fail
from services.gl_service import GL_ACCOUNTS, GLService
from utils.gl_reference_types import GLRef


def post_sale_commissions(sale):
    entries = PartnerCommissionEntry.query.filter_by(sale_id=sale.id, tenant_id=sale.tenant_id).all()
    if not entries:
        return None

    total = sum(Decimal(str(e.commission_amount_aed or 0)) for e in entries)
    if total <= Decimal('0'):
        return None

    # Dynamic currency: use sale's exchange rate and base currency
    exchange_rate = Decimal(str(sale.exchange_rate)) if sale.exchange_rate else Decimal('1')
    base_currency = getattr(sale, 'currency', 'AED')
    try:
        from utils.currency_utils import resolve_tenant_base_currency
        base_currency = resolve_tenant_base_currency(tenant_id=sale.tenant_id) or base_currency
    except Exception:
        pass

    GLService.ensure_core_accounts(tenant_id=getattr(sale, 'tenant_id', None))
    return post_or_fail(
        [
            {
                'account': GL_ACCOUNTS['commission_expense'],
                'concept_code': 'COMMISSION_EXPENSE',
                'debit': total,
                'description': f'عمولات شركاء — {sale.sale_number}',
            },
            {
                'account': GL_ACCOUNTS['partner_current_account'],
                'concept_code': 'PARTNER_CURRENT_ACCOUNT',
                'credit': total,
                'description': f'جاري شركاء — {sale.sale_number}',
            },
        ],
        description=f'Partner commissions {sale.sale_number}',
        reference_type=GLRef.PARTNER_COMMISSION,
        reference_id=sale.id,
        exchange_rate=exchange_rate,
        branch_id=sale.branch_id,
        tenant_id=getattr(sale, 'tenant_id', None),
    )
