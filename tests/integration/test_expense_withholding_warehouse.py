"""Exercise the expense route and warehouse totals against real ledger rows."""

from datetime import UTC, datetime
from decimal import Decimal

from models import Expense, GLAccount, GLJournalEntry, GLJournalLine, Warehouse
from services.partner_service import PartnerService
from utils.gl_reference_types import GLRef


def test_withholding_posts_balanced_and_warehouse_cost_is_attributed(
    auth_client, db_session, sample_tenant, sample_warehouse, sample_expense_category
):
    sample_tenant.wht_services_rate = Decimal("5")
    db_session.commit()
    response = auth_client.post(
        "/expenses/create",
        data={
            "amount": "100",
            "currency": "AED",
            "description": "Nonresident service",
            "category_id": str(sample_expense_category.id),
            "payment_method": "cash",
            "is_service_to_nonresident": "on",
            "warehouse_id": str(sample_warehouse.id),
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    expense = db_session.query(Expense).filter_by(tenant_id=sample_tenant.id, description="Nonresident service").one()
    assert expense.wht_amount == Decimal("5.000")
    assert expense.branch_id == sample_warehouse.branch_id
    assert expense.warehouse_id == sample_warehouse.id

    entry = (
        db_session.query(GLJournalEntry)
        .filter_by(tenant_id=sample_tenant.id, reference_type=GLRef.EXPENSE, reference_id=expense.id, status="posted")
        .one()
    )
    lines = (
        db_session.query(GLJournalLine, GLAccount)
        .join(GLAccount, GLJournalLine.account_id == GLAccount.id)
        .filter(GLJournalLine.entry_id == entry.id)
        .all()
    )
    assert sum((line.debit or Decimal("0") for line, _ in lines), Decimal("0")) == Decimal("100.000")
    assert sum((line.credit or Decimal("0") for line, _ in lines), Decimal("0")) == Decimal("100.000")
    assert sum((line.credit for line, account in lines if account.code == "2149"), Decimal("0")) == Decimal("5.000")
    assert sum((line.credit for line, account in lines if account.code.startswith("1110")), Decimal("0")) == Decimal(
        "95.000"
    )
    today = datetime.now(UTC).date()
    assert PartnerService.get_scope_expenses(
        sample_tenant.id, today, today, "warehouse", sample_warehouse.id
    ) == Decimal("100.000")
    assert PartnerService.get_scope_expenses(
        sample_tenant.id + 999999, today, today, "warehouse", sample_warehouse.id
    ) == Decimal("0")

    edited = auth_client.post(
        f"/expenses/{expense.id}/edit",
        data={"amount": "200", "currency": "AED", "category_id": str(sample_expense_category.id)},
    )
    assert edited.status_code == 200
    db_session.expire_all()
    assert db_session.get(Expense, expense.id).amount == Decimal("100.000")

    assert auth_client.post(f"/expenses/{expense.id}/cancel").status_code == 302
    db_session.expire_all()
    assert db_session.get(Expense, expense.id).is_reversed is True
    entries = (
        db_session.query(GLJournalEntry)
        .filter_by(tenant_id=sample_tenant.id, reference_type=GLRef.EXPENSE, reference_id=expense.id)
        .all()
    )
    assert len(entries) == 2
    withholding_lines = (
        db_session.query(GLJournalLine)
        .join(GLAccount, GLJournalLine.account_id == GLAccount.id)
        .filter(GLJournalLine.entry_id.in_([entry.id for entry in entries]), GLAccount.code == "2149")
        .all()
    )
    assert sum((line.debit - line.credit for line in withholding_lines), Decimal("0")) == Decimal("0")
    assert PartnerService.get_scope_expenses(
        sample_tenant.id, today, today, "warehouse", sample_warehouse.id
    ) == Decimal("0")
    assert auth_client.post(f"/expenses/{expense.id}/cancel").status_code == 302
    assert (
        db_session.query(GLJournalEntry)
        .filter_by(tenant_id=sample_tenant.id, reference_type=GLRef.EXPENSE, reference_id=expense.id)
        .count()
        == 2
    )


def test_missing_wht_rate_and_cheque_are_refused_without_writes(
    auth_client, db_session, sample_tenant, sample_warehouse, sample_expense_category
):
    data = {
        "amount": "100",
        "currency": "AED",
        "description": "Refused withholding",
        "category_id": str(sample_expense_category.id),
        "payment_method": "cash",
        "is_service_to_nonresident": "on",
        "warehouse_id": str(sample_warehouse.id),
    }
    sample_tenant.wht_services_rate = None
    db_session.commit()
    assert auth_client.post("/expenses/create", data=data).status_code == 200
    assert db_session.query(Expense).filter_by(tenant_id=sample_tenant.id, description=data["description"]).count() == 0

    sample_tenant.wht_services_rate = Decimal("5")
    db_session.commit()
    data["payment_method"] = "cheque"
    assert auth_client.post("/expenses/create", data=data).status_code == 200
    assert db_session.query(Expense).filter_by(tenant_id=sample_tenant.id, description=data["description"]).count() == 0


def test_warehouse_expenses_exclude_other_warehouses_pending_and_reversed(
    db_session, sample_tenant, sample_warehouse, sample_expense_category, sample_user
):
    other = Warehouse(tenant_id=sample_tenant.id, branch_id=sample_warehouse.branch_id, name="Other expense warehouse")
    db_session.add(other)
    db_session.flush()
    for number, warehouse, amount, status, reversed_ in (
        ("EXP-WH-A", sample_warehouse, "15", "confirmed", False),
        ("EXP-WH-B", other, "25", "confirmed", False),
        ("EXP-WH-C", sample_warehouse, "50", "pending", False),
        ("EXP-WH-D", sample_warehouse, "75", "confirmed", True),
    ):
        db_session.add(
            Expense(
                tenant_id=sample_tenant.id,
                branch_id=sample_warehouse.branch_id,
                warehouse_id=warehouse.id,
                category_id=sample_expense_category.id,
                user_id=sample_user.id,
                expense_number=number,
                description=number,
                amount=Decimal(amount),
                amount_aed=Decimal(amount),
                payment_method="cash",
                status=status,
                is_reversed=reversed_,
            )
        )
    db_session.flush()
    today = datetime.now(UTC).date()
    assert PartnerService.get_scope_expenses(
        sample_tenant.id, today, today, "warehouse", sample_warehouse.id
    ) == Decimal("15.000")
    assert PartnerService.get_scope_expenses(sample_tenant.id, today, today, "warehouse", other.id) == Decimal("25.000")
    assert PartnerService.get_scope_expenses(
        sample_tenant.id, today, today, "branch", sample_warehouse.branch_id
    ) == Decimal("40.000")
