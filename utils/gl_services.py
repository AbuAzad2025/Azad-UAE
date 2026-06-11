"""
GL service wrappers for use by models.
Provides access to GL posting and account resolution functions
without models importing directly from services/.
"""


def gl_ensure_core_accounts(tenant_id=None):
    from services.gl_service import GLService
    return GLService.ensure_core_accounts(tenant_id=tenant_id)


def gl_get_customer_credit_account(customer, branch_id=None, tenant_id=None):
    from services.gl_service import GLService
    return GLService.get_customer_credit_account(customer, branch_id=branch_id, tenant_id=tenant_id)


def gl_get_customer_credit_concept(customer):
    from services.gl_service import GLService
    return GLService.get_customer_credit_concept(customer)


def gl_get_default_liquidity_account(liquidity_kind='bank', tenant_id=None, branch_id=None):
    from services.gl_service import GLService
    return GLService.get_default_liquidity_account(liquidity_kind, branch_id=branch_id, tenant_id=tenant_id)


def gl_create_manual_entry(*args, **kwargs):
    from services.gl_service import GLService
    return GLService.create_manual_entry(*args, **kwargs)


def gl_post_or_fail(lines, description, reference_type, reference_id,
                    currency='AED', exchange_rate=1.0, branch_id=None,
                    tenant_id=None):
    from services.gl_posting import post_or_fail
    return post_or_fail(
        lines=lines,
        description=description,
        reference_type=reference_type,
        reference_id=reference_id,
        currency=currency,
        exchange_rate=exchange_rate,
        branch_id=branch_id,
        tenant_id=tenant_id,
    )


def gl_resolve_exchange_rate(transaction_date, from_currency, to_currency='AED', tenant_id=None):
    from services.exchange_rate_service import ExchangeRateService
    return ExchangeRateService.resolve_exchange_rate_for_transaction(
        transaction_date=transaction_date,
        from_currency=from_currency,
        to_currency=to_currency,
        tenant_id=tenant_id,
    )


def gl_next_entry_number(tenant_id):
    from services.gl_helpers import next_entry_number
    return next_entry_number(tenant_id)


def gl_post_entry(*args, **kwargs):
    from services.gl_service import GLService
    return GLService.post_entry(*args, **kwargs)
