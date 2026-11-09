"""Withholding is calculated from an explicit tenant rate, not guessed."""

from decimal import Decimal

import pytest

from services.expense_service import ExpenseService


@pytest.mark.parametrize(
    ("amount", "rate", "applies", "expected"),
    [
        ("100", "5", True, "5.000"),
        ("2.001", "12.5", True, "0.250"),
        ("100", "0", True, "0.000"),
        ("100", "100", True, "100.000"),
        ("100", None, False, "0.000"),
    ],
)
def test_withholding_amount(amount, rate, applies, expected):
    assert ExpenseService.calculate_withholding(amount, rate, applies) == Decimal(expected)


@pytest.mark.parametrize(
    ("amount", "rate"),
    [("100", None), ("100", "NaN"), ("100", "Infinity"), ("100", "-1"), ("100", "101"), ("0", "5")],
)
def test_withholding_refuses_unknown_or_invalid_rates(app, amount, rate):
    with app.app_context(), pytest.raises(ValueError):
        ExpenseService.calculate_withholding(amount, rate, True)


def test_warehouse_validation_checks_tenant_branch_and_active_state(
    db_session, sample_tenant, sample_warehouse, sample_branch
):
    from models import Branch, Tenant, Warehouse

    other_branch = Branch(tenant_id=sample_tenant.id, name="Other branch", code="OTHER")
    other_tenant = Tenant(name="Other tenant", slug="wh-other", name_ar="Other")
    db_session.add_all([other_branch, other_tenant])
    db_session.flush()
    inactive = Warehouse(tenant_id=sample_tenant.id, branch_id=sample_branch.id, name="Inactive", is_active=False)
    foreign = Warehouse(tenant_id=other_tenant.id, name="Foreign", is_active=True)
    db_session.add_all([inactive, foreign])
    db_session.flush()

    assert ExpenseService.resolve_warehouse(sample_warehouse.id, sample_tenant.id, sample_branch.id) == sample_warehouse
    for warehouse_id, branch_id in (
        (sample_warehouse.id, other_branch.id),
        (inactive.id, sample_branch.id),
        (foreign.id, None),
        (9999999, None),
    ):
        with pytest.raises(ValueError):
            ExpenseService.resolve_warehouse(warehouse_id, sample_tenant.id, branch_id)
