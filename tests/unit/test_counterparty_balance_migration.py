"""The data-repair migration rebuilds balances from the historical documents."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal


def _run_migration(db_session, mocker):
    import importlib

    migration = importlib.import_module("migrations.versions.f5a6b7c8d9e0_repair_counterparty_balances")
    mocker.patch.object(migration.op, "get_bind", return_value=db_session.connection())
    migration.upgrade()
    db_session.expire_all()
    return migration


def test_migration_repairs_all_counterparty_balances(
    db_session, mocker, sample_tenant, sample_customer, sample_user, sample_warehouse, sample_product, sample_supplier
):
    from models import (
        MaintenanceInvoice,
        MaintenanceOrder,
        MaintenanceReceipt,
        MaintenanceReturn,
        Partner,
        PartnerCommissionEntry,
        PartnerTransaction,
        Payment,
        Sale,
        Supplier,
    )
    from models.maintenance import MaintenancePurchaseOrder, MaintenancePurchaseOrderStatus

    tid = sample_tenant.id
    # Trade movement: a sale of 100 with 40 already paid leaves a 60 debt.
    db_session.add(
        Sale(
            tenant_id=tid,
            sale_number="MIG-SALE-1",
            customer_id=sample_customer.id,
            seller_id=sample_user.id,
            sale_date=datetime.now(UTC),
            status="confirmed",
            subtotal=Decimal("100"),
            total_amount=Decimal("100"),
            amount=Decimal("100"),
            amount_aed=Decimal("100"),
            balance_due=Decimal("60"),
            currency="AED",
        )
    )
    db_session.add(
        Payment(
            tenant_id=tid,
            customer_id=sample_customer.id,
            payment_number="MIG-PAY-1",
            payment_type="sale_payment",
            reference_number="MIG-PAY-1",
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

    # Maintenance movements net to zero: invoice -30, receipt +30,
    # return +10, refund -10.
    order = MaintenanceOrder(
        tenant_id=tid,
        order_number="MIG-MORD-1",
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
    db_session.add_all(
        [
            MaintenanceInvoice(
                tenant_id=tid,
                order_id=order.id,
                invoice_number="MIG-MINV-1",
                total_amount=Decimal("30"),
                amount=Decimal("30"),
                amount_aed=Decimal("30"),
                currency="AED",
                base_currency="AED",
                posted=True,
            ),
            MaintenanceReceipt(
                tenant_id=tid,
                order_id=order.id,
                receipt_number="MIG-PT-1",
                amount=Decimal("30"),
                payment_mode="cash",
                cashier_id=sample_user.id,
            ),
            MaintenanceReturn(
                tenant_id=tid,
                order_id=order.id,
                return_number="MIG-MRET-1",
                returned_by=sample_user.id,
                total_value=Decimal("10"),
                total_value_aed=Decimal("10"),
                posted=True,
            ),
            MaintenanceReceipt(
                tenant_id=tid,
                order_id=order.id,
                receipt_number="MIG-PT-REFUND-1",
                amount=Decimal("10"),
                payment_mode="cash",
                cashier_id=sample_user.id,
                is_refund=True,
            ),
        ]
    )

    # A workshop purchase the supplier was never charged for.
    db_session.add(
        MaintenancePurchaseOrder(
            tenant_id=tid,
            supplier_id=sample_supplier.id,
            po_number="MIG-MPO-1",
            status=MaintenancePurchaseOrderStatus.RECEIVED,
            total_amount=Decimal("200"),
            currency="AED",
            exchange_rate=Decimal("1"),
            posted=True,
        )
    )

    # A sale commission the partner ledger never saw.
    partner = Partner(
        tenant_id=tid,
        code="MIG-PARTNER",
        name="شريك ترحيل",
        share_percentage=Decimal("50"),
        current_balance=Decimal("0"),
    )
    db_session.add(partner)
    db_session.flush()
    sample_customer.partner_id = partner.id
    sale = Sale.query.filter_by(sale_number="MIG-SALE-1").one()
    db_session.add(
        PartnerCommissionEntry(
            tenant_id=tid,
            sale_id=sale.id,
            partner_customer_id=sample_customer.id,
            percentage=Decimal("5"),
            base_amount_aed=Decimal("1000"),
            commission_amount_aed=Decimal("50"),
        )
    )

    # Deliberately break the stored conveniences.
    sample_customer.balance = Decimal("999")
    sample_supplier.total_purchases_aed = Decimal("0")
    partner.current_balance = Decimal("0")
    db_session.flush()

    _run_migration(db_session, mocker)

    assert Decimal(str(sample_customer.balance)) == Decimal("-60.000")
    assert Decimal(str(Supplier.query.get(sample_supplier.id).total_purchases_aed)) == Decimal("200.000")
    assert Decimal(str(Partner.query.get(partner.id).current_balance)) == Decimal("50.000")
    tx = PartnerTransaction.query.filter_by(
        partner_id=partner.id, reference_type="sale_commission", reference_id=sale.id
    ).one()
    assert Decimal(str(tx.amount_base)) == Decimal("50.000")
    assert Decimal(str(tx.balance_after)) == Decimal("50.000")


def test_migration_is_idempotent(db_session, mocker, sample_tenant, sample_customer, sample_user):
    from models import Partner, PartnerCommissionEntry, PartnerTransaction, Sale

    tid = sample_tenant.id
    partner = Partner(
        tenant_id=tid,
        code="MIG-PARTNER-2",
        name="شريك ترحيل ٢",
        share_percentage=Decimal("50"),
        current_balance=Decimal("0"),
    )
    db_session.add(partner)
    db_session.flush()
    sample_customer.partner_id = partner.id
    sale = Sale(
        tenant_id=tid,
        sale_number="MIG-SALE-2",
        customer_id=sample_customer.id,
        seller_id=sample_user.id,
        sale_date=datetime.now(UTC),
        status="confirmed",
        total_amount=Decimal("100"),
        amount=Decimal("100"),
        amount_aed=Decimal("100"),
        currency="AED",
    )
    db_session.add(sale)
    db_session.flush()
    db_session.add(
        PartnerCommissionEntry(
            tenant_id=tid,
            sale_id=sale.id,
            partner_customer_id=sample_customer.id,
            percentage=Decimal("5"),
            base_amount_aed=Decimal("1000"),
            commission_amount_aed=Decimal("25"),
        )
    )
    db_session.flush()

    migration = _run_migration(db_session, mocker)
    assert PartnerTransaction.query.filter_by(reference_type="sale_commission", reference_id=sale.id).count() == 1
    assert Decimal(str(Partner.query.get(partner.id).current_balance)) == Decimal("25.000")

    # A second run finds the row already present and leaves it alone.
    mocker.patch.object(migration.op, "get_bind", return_value=db_session.connection())
    migration.upgrade()
    db_session.expire_all()
    assert PartnerTransaction.query.filter_by(reference_type="sale_commission", reference_id=sale.id).count() == 1
    assert Decimal(str(Partner.query.get(partner.id).current_balance)) == Decimal("25.000")
