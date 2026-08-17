"""
Budget enforcement helper — shared by PurchaseService and expense routes.
"""

from decimal import Decimal


def check_budget_for_account(tenant_id, account_code, amount, branch_id=None):
    """
    Find the active budget for a tenant and check if the given amount
    would exceed the budget for the specified GL account.

    Returns dict with allowed, message, enforcement, budgeted, actual, remaining.
    Returns None if no active budget exists (fast path).
    """
    from models import Budget
    from utils.tenanting import tenant_query

    active_budgets = tenant_query(Budget).filter_by(tenant_id=tenant_id, status="active")
    if branch_id is not None:
        active_budgets = active_budgets.filter((Budget.branch_id == branch_id) | (Budget.branch_id.is_(None)))

    budget = active_budgets.first()
    if not budget:
        return None

    from models import GLAccount

    account = GLAccount.query.filter_by(
        tenant_id=tenant_id,
        code=str(account_code),
    ).first()
    if not account:
        return None

    return budget.check_budget(account.id, Decimal(str(amount)))
