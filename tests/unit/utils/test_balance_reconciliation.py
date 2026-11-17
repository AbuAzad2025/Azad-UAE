"""The historical reconciler rebuilds cached balances from every document."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from utils.balance_reconciliation import reconcile


def test_full_historical_reconciliation(db_session, sample_tenant, sample_customer, sample_user, sample_supplier):
    from models import (
        MaintenanceInvoice,
        MaintenanceOrder,
        MaintenanceReceipt,
        Partner,
        PartnerTransaction,
        Payment,
        Purchase,
        Sale,
    )
    from models.receipt import Receipt

    tid = sample_tenant.id
    sale = Sale(
        tenant_id=tid,
        sale_number="RECON-SALE-1",
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        sale_date=datetime.now(UTC),
        status="confirmed",
        amount_aed=Decimal("100"),
        total_amount=Decimal("100"),
        amount=Decimal("100"),
        subtotal=Decimal("100"),
    )
    db_session.add(sale)
    db_session.add(
        Payment(
            tenant_id=tid,
            customer_id=sample_customer.id,
            payment_number="RECON-PAY-1",
            payment_type="sale_payment",
            direction="incoming",
            amount=Decimal("40"),
            amount_aed=Decimal("40"),
            currency="AED",
            exchange_rate=Decimal("1"),
            payment_method="cash",
            payment_confirmed=True,
            payment_date=datetime.now(UTC),
        )
    )
    db_session.add(
        Receipt(
            tenant_id=tid,
            receipt_number="RECON-RCPT-1",
            customer_id=sample_customer.id,
            amount=Decimal("10"),
            amount_aed=Decimal("10"),
            currency="AED",
            exchange_rate=Decimal("1"),
            payment_method="cash",
            payment_confirmed=True,
            receipt_date=datetime.now(UTC),
        )
    )
    order = MaintenanceOrder(
        tenant_id=tid,
        order_number="RECON-MORD-1",
        customer_id=sample_customer.id,
        received_by=sample_user.id,
        total_amount=Decimal("30"),
        amount=Decimal("30"),
        amount_aed=Decimal("30"),
        currency="AED",
        base_currency="AED",
        exchange_rate=Decimal("1"),
        status="closed",
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        MaintenanceInvoice(
            tenant_id=tid,
            order_id=order.id,
            invoice_number="RECON-MINV-1",
            invoice_date=datetime.now(UTC),
            amount=Decimal("30"),
            amount_aed=Decimal("30"),
            total_amount=Decimal("30"),
            posted=True,
        )
    )
    db_session.add(
        MaintenanceReceipt(
            tenant_id=tid,
            order_id=order.id,
            receipt_number="RECON-MRCPT-1",
            amount=Decimal("30"),
            payment_mode="cash",
            cashier_id=sample_user.id,
        )
    )
    db_session.add(
        Purchase(
            tenant_id=tid,
            supplier_id=sample_supplier.id,
            supplier_name=sample_supplier.name,
            purchase_number="RECON-PUR-1",
            user_id=sample_user.id,
            status="confirmed",
            amount=Decimal("200"),
            amount_aed=Decimal("200"),
            total_amount=Decimal("200"),
        )
    )
    db_session.add(
        Payment(
            tenant_id=tid,
            supplier_id=sample_supplier.id,
            payment_number="RECON-SPAY-1",
            payment_type="supplier_payment",
            direction="outgoing",
            amount=Decimal("50"),
            amount_aed=Decimal("50"),
            currency="AED",
            exchange_rate=Decimal("1"),
            payment_method="cash",
            payment_confirmed=True,
            payment_date=datetime.now(UTC),
        )
    )
    partner = Partner(
        tenant_id=tid,
        code="RECON-PARTNER",
        name="Recon Partner",
        current_balance=Decimal("0"),
        share_percentage=Decimal("50"),
    )
    db_session.add(partner)
    db_session.flush()
    db_session.add(
        PartnerTransaction(
            tenant_id=tid,
            partner_id=partner.id,
            transaction_type="profit_share",
            amount=Decimal("75"),
            amount_base=Decimal("75"),
            balance_after=Decimal("0"),
            transaction_date=datetime.now(UTC).date(),
        )
    )

    # Corrupt every cached balance.
    sample_customer.balance = Decimal("999")
    sample_supplier.total_purchases_aed = Decimal("1")
    sample_supplier.total_paid_aed = Decimal("1")
    partner.current_balance = Decimal("1")
    db_session.flush()

    preview = reconcile(db_session.connection(), apply=False)
    assert preview["total_discrepancies"] >= 3
    assert sample_customer.balance == Decimal("999")  # dry-run changed nothing

    report = reconcile(db_session.connection(), apply=True)
    db_session.expire_all()

    # -100 sale +40 payment +10 receipt -30 invoice +30 maintenance receipt = -50
    assert sample_customer.balance == Decimal("-50.000")
    assert sample_supplier.total_purchases_aed == Decimal("200.000")
    assert sample_supplier.total_paid_aed == Decimal("50.000")
    assert partner.current_balance == Decimal("75.000")
    assert report["total_discrepancies"] >= 3

    # Applying twice is idempotent.
    assert reconcile(db_session.connection(), apply=True)["total_discrepancies"] == 0


def test_maintenance_receipt_is_converted_at_the_order_rate(db_session, sample_tenant, sample_customer, sample_user):
    """A foreign-currency workshop receipt must reach the balance in base currency.

    Regression: the first version of the reconciler read the raw receipt amount,
    which would overwrite a correct 35.00 AED balance with 10.00 on upgrade.
    """
    from models import MaintenanceOrder, MaintenanceReceipt

    tid = sample_tenant.id
    order = MaintenanceOrder(
        tenant_id=tid,
        order_number="RECON-FX-ORDER",
        customer_id=sample_customer.id,
        received_by=sample_user.id,
        total_amount=Decimal("100"),
        amount=Decimal("100"),
        amount_aed=Decimal("350"),
        currency="USD",
        exchange_rate=Decimal("3.5"),
        base_currency="AED",
        status="closed",
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(
        MaintenanceReceipt(
            tenant_id=tid,
            order_id=order.id,
            receipt_number="RECON-FX-RCPT",
            amount=Decimal("10"),  # 10 USD at 3.5 => 35 AED
            payment_mode="cash",
            cashier_id=sample_user.id,
        )
    )
    sample_customer.balance = Decimal("0")
    db_session.flush()

    reconcile(db_session.connection(), apply=True)
    db_session.expire_all()

    assert sample_customer.balance == Decimal("35.000")


def test_cash_box_and_customer_total_purchases_are_rebuilt(
    db_session, sample_tenant, sample_customer, sample_user, sample_gl_accounts
):
    """The two cached columns with no incremental writer are rebuilt too."""
    from models import GLAccount, GLJournalEntry, GLJournalLine, Sale
    from models.cash_box import CashBox

    tid = sample_tenant.id
    cash_account = GLAccount.query.filter_by(tenant_id=tid, code="1111").first()
    assert cash_account is not None

    db_session.add(
        Sale(
            tenant_id=tid,
            sale_number="RECON-TP-SALE",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            sale_date=datetime.now(UTC),
            status="confirmed",
            is_active=True,
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            total_amount=Decimal("100"),
        )
    )
    entry = GLJournalEntry(
        tenant_id=tid,
        entry_number="RECON-CB-GL",
        entry_date=datetime.now(UTC),
        description="cash box reconciliation",
        reference_type="manual",
        currency="AED",
        exchange_rate=Decimal("1"),
        total_debit=Decimal("55"),
        total_credit=Decimal("55"),
        status="posted",
        is_posted=True,
    )
    db_session.add(entry)
    db_session.flush()
    db_session.add(
        GLJournalLine(
            tenant_id=tid,
            entry_id=entry.id,
            account_id=cash_account.id,
            debit=Decimal("55"),
            credit=Decimal("0"),
            amount=Decimal("55"),
            amount_aed=Decimal("55"),
        )
    )
    box = CashBox(
        tenant_id=tid,
        code="RECON-CB",
        name_ar="صندوق",
        box_type="cash",
        currency="AED",
        current_balance=Decimal("999"),
        gl_account_id=cash_account.id,
    )
    db_session.add(box)
    sample_customer.total_purchases = Decimal("1")
    db_session.flush()

    report = reconcile(db_session.connection(), apply=True)
    db_session.expire_all()

    assert any(c["id"] == box.id for c in report["cash_boxes"])
    assert box.current_balance == Decimal("55.000")
    assert sample_customer.total_purchases == Decimal("100.000")
