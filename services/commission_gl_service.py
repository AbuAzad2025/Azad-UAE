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
                'account': '3350',
                'concept_code': 'PARTNER_CURRENT_ACCOUNT',
                'credit': total,
                'description': f'جاري شركاء — {sale.sale_number}',
            },
        ],
        description=f'Partner commissions {sale.sale_number}',
        reference_type=GLRef.PARTNER_COMMISSION,
        reference_id=sale.id,
        exchange_rate=1.0,
        branch_id=sale.branch_id,
        tenant_id=getattr(sale, 'tenant_id', None),
    )
