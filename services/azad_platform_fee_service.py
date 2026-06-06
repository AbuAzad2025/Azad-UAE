"""Azad platform fee accruals for tenant online-store payments."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from flask import current_app

from extensions import db
from models import AzadPlatformFee
from models.payment_vault import PaymentVault
from services.gl_posting import post_or_fail
from services.gl_service import GL_ACCOUNTS, GLService
from utils.gl_reference_types import GLRef


class AzadPlatformFeeService:
    RATE = Decimal('0.01')
    RATE_PERCENT = Decimal('1.00')

    @staticmethod
    def is_online_store_transaction(sale) -> bool:
        if getattr(sale, 'source', None) != 'online_store':
            return False
        channel = (getattr(sale, 'checkout_payment_method', None) or '').strip().lower()
        gateway_ref = (getattr(sale, 'checkout_gateway_ref', None) or '').strip()
        return channel == 'online_pay' or bool(gateway_ref)

    @staticmethod
    def _base_amount_aed(sale, payment=None) -> Decimal:
        if payment is not None and getattr(payment, 'amount_aed', None) is not None:
            amount = Decimal(str(payment.amount_aed or 0))
        else:
            amount = Decimal(str(getattr(sale, 'amount_aed', None) or getattr(sale, 'total_amount', 0) or 0))
        return amount.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)

    @staticmethod
    def _idempotency_key(sale, payment=None, gateway_reference=None) -> str:
        tenant_id = int(getattr(sale, 'tenant_id'))
        sale_id = int(getattr(sale, 'id'))
        ref = (
            gateway_reference
            or getattr(sale, 'checkout_gateway_ref', None)
            or getattr(payment, 'id', None)
            or 'sale'
        )
        return f'store-online:{tenant_id}:{sale_id}:{ref}'

    @staticmethod
    def record_store_online_fee(
        sale,
        *,
        payment=None,
        payment_channel=None,
        gateway_name='nowpayments',
        gateway_reference=None,
    ) -> AzadPlatformFee | None:
        """Record and post Azad's 1% share for a confirmed online-store payment."""
        if not AzadPlatformFeeService.is_online_store_transaction(sale):
            return None

        tenant_id = getattr(sale, 'tenant_id', None)
        if tenant_id is None:
            raise ValueError('Online store sale is missing tenant_id.')

        key = AzadPlatformFeeService._idempotency_key(sale, payment, gateway_reference)
        existing = AzadPlatformFee.query.filter_by(idempotency_key=key).first()
        if existing:
            return existing

        base_amount = AzadPlatformFeeService._base_amount_aed(sale, payment)
        if base_amount <= Decimal('0'):
            return None

        fee_amount = (base_amount * AzadPlatformFeeService.RATE).quantize(
            Decimal('0.001'), rounding=ROUND_HALF_UP
        )
        if fee_amount <= Decimal('0'):
            return None

        vault = PaymentVault.get_platform_vault()
        fee = AzadPlatformFee(
            idempotency_key=key,
            tenant_id=int(tenant_id),
            sale_id=int(sale.id),
            payment_id=getattr(payment, 'id', None),
            vault_id=getattr(vault, 'id', None),
            rate_percent=AzadPlatformFeeService.RATE_PERCENT,
            base_amount_aed=base_amount,
            fee_amount_aed=fee_amount,
            payment_channel=(payment_channel or getattr(sale, 'checkout_payment_method', None) or 'online_pay')[:50],
            gateway_name=gateway_name,
            gateway_reference=(gateway_reference or getattr(sale, 'checkout_gateway_ref', None) or '')[:120],
            status='accrued',
        )
        db.session.add(fee)
        db.session.flush()

        GLService.ensure_core_accounts(tenant_id=int(tenant_id))
        post_or_fail(
            [
                {
                    'account': GL_ACCOUNTS['commission_expense'],
                    'concept_code': 'COMMISSION_EXPENSE',
                    'debit': fee_amount,
                    'description': f'Azad online platform fee 1% - {sale.sale_number}',
                },
                {
                    'account': GL_ACCOUNTS['payable'],
                    'concept_code': 'AP',
                    'credit': fee_amount,
                    'description': f'Azad payable - online platform fee {sale.sale_number}',
                },
            ],
            description=f'Azad platform fee {sale.sale_number}',
            reference_type=GLRef.AZAD_PLATFORM_FEE,
            reference_id=fee.id,
            currency='AED',
            exchange_rate=1.0,
            branch_id=getattr(sale, 'branch_id', None),
            tenant_id=int(tenant_id),
        )
        fee.gl_posted = True
        current_app.logger.info('Azad platform fee accrued: sale=%s fee=%s', sale.sale_number, fee_amount)
        return fee
