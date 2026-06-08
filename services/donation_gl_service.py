"""GL posting for completed Azad donations — owner vault integration."""
from __future__ import annotations

from decimal import Decimal

from flask import current_app

from extensions import db
from models.donation import Donation
from models import GLAccount
from models.payment_vault import PaymentVault
from services.exchange_rate_service import ExchangeRateService
from services.gl_service import GLService
from services.gl_posting import post_or_fail
from utils.gl_reference_types import GLRef


class DonationGLService:
    @staticmethod
    def _vault_accounts(vault: PaymentVault | None, tenant_id: int) -> tuple[str, str]:
        debit = (getattr(vault, 'donation_debit_account', None) or '1120').strip()
        credit = (getattr(vault, 'donation_credit_account', None) or '4200').strip()
        debit_account = GLAccount.query.filter_by(code=debit, tenant_id=tenant_id).order_by(GLAccount.id.asc()).first()
        if debit in ('1110', '1120') or getattr(debit_account, 'is_header', False):
            debit = GLService.get_default_liquidity_account('bank', tenant_id=tenant_id)
        return debit, credit

    @staticmethod
    def post_completed_donation(donation: Donation) -> bool:
        if getattr(donation, 'gl_posted', False):
            return True
        if donation.status != 'completed':
            return False

        amount_usd = Decimal(str(donation.amount_usd or 0))
        if amount_usd <= 0:
            return False

        tenant_id = getattr(donation, 'tenant_id', None)
        if tenant_id is None:
            current_app.logger.info(
                'Skipping tenant GL posting for Azad/platform donation #%s; platform ledger is not tenant-scoped.',
                getattr(donation, 'id', None),
            )
            return False

        vault = PaymentVault.get_tenant_vault(tenant_id) or PaymentVault.get_platform_vault()
        debit_acct, credit_acct = DonationGLService._vault_accounts(vault, tenant_id)

        try:
            rate_info = ExchangeRateService.resolve_exchange_rate_for_transaction('USD', 'AED')
            rate = Decimal(str(rate_info['rate']))
        except Exception:
            rate = Decimal('3.67')
        amount_aed = (amount_usd * rate).quantize(Decimal('0.001'))

        method_label = donation.payment_method or 'donation'
        donor = donation.donor_name or donation.customer_name or 'متبرع'
        desc = f'تبرع Azad #{donation.id} — {donor} ({method_label})'

        lines = [
            {'account': debit_acct, 'concept_code': 'BANK', 'debit': amount_aed, 'description': desc},
            {'account': credit_acct, 'concept_code': 'DONATION_REVENUE', 'credit': amount_aed, 'description': desc},
        ]

        try:
            post_or_fail(
                lines,
                description=desc,
                reference_type=GLRef.DONATION,
                reference_id=donation.id,
                exchange_rate=1,
                tenant_id=tenant_id,
            )
            donation.gl_posted = True
            db.session.flush()
            current_app.logger.info(f'Donation GL posted: #{donation.id} AED {amount_aed}')
            return True
        except Exception as exc:
            current_app.logger.error(f'Donation GL failed #{donation.id}: {exc}')
            raise
