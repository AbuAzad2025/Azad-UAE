"""E2E dry-run simulation — exercises the full POS→GL→Shift→Billing lifecycle.

Runs as a standalone script (python tests/e2e_dry_run.py) or via pytest.
Creates an isolated tenant, opens a POS shift, processes a sale with VAT,
verifies balanced GL journal entries, reconciles/closes the shift, and
runs the subscription scheduler to verify expiry detection.
"""

import sys
import uuid
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)


def _setup():
    from app.factory import create_app
    from config import TestConfig
    from extensions import db

    app = create_app(config_class=TestConfig)
    with app.app_context():
        db.create_all()
    return app, db


def _seed_tenant(db):
    from models import Tenant, Branch, Warehouse, Role, User, Customer, Product
    from models.system_settings import SystemSettings

    uid = uuid.uuid4().hex[:8]

    tenant = Tenant(
        name=f"E2E {uid}",
        name_ar=f"E2E {uid}",
        slug=f"e2e-{uid}",
        default_currency="AED",
        base_currency="AED",
        enable_tax=True,
        default_tax_rate=Decimal("5.00"),
        enable_pos=True,
        is_active=True,
        is_suspended=False,
        subscription_plan="pro",
        subscription_plan_duration="monthly",
        subscription_end=datetime.now(timezone.utc) + timedelta(days=2),
        max_users=10,
        max_branches=5,
        max_products=1000,
        max_customers=500,
        max_suppliers=200,
    )
    db.session.add(tenant)
    db.session.flush()

    branch = Branch(tenant_id=tenant.id, name=f"Main {uid}", code=f"B{uid[:4]}")
    db.session.add(branch)
    db.session.flush()

    wh = Warehouse(
        tenant_id=tenant.id,
        name=f"WH {uid}",
        branch_id=branch.id,
        allow_negative_inventory=True,
    )
    db.session.add(wh)
    db.session.flush()

    role = Role(name=f"Cashier {uid}", slug="cashier", is_active=True)
    db.session.add(role)
    db.session.flush()

    user = User(
        tenant_id=tenant.id,
        username=f"cashier_{uid}",
        email=f"cashier_{uid}@e2e.test",
        full_name="E2E Cashier",
        role_id=role.id,
        branch_id=branch.id,
    )
    user.set_password("test123")
    db.session.add(user)
    db.session.flush()

    customer = Customer(tenant_id=tenant.id, name=f"Walk-in {uid}", phone="0500000000")
    db.session.add(customer)
    db.session.flush()

    product = Product(
        tenant_id=tenant.id,
        name=f"Item {uid}",
        name_ar=f"منتج {uid}",
        sku=f"SKU-{uid}",
        cost_price=Decimal("50"),
        regular_price=Decimal("100"),
        current_stock=Decimal("100"),
        is_active=True,
    )
    db.session.add(product)
    db.session.flush()

    settings = SystemSettings.query.first()
    if not settings:
        settings = SystemSettings(
            enable_pos=True, enable_tax=True, default_tax_rate=Decimal("5.00")
        )
        db.session.add(settings)
    else:
        settings.enable_pos = True
        settings.enable_tax = True
    db.session.flush()

    return {
        "tenant": tenant,
        "branch": branch,
        "warehouse": wh,
        "user": user,
        "customer": customer,
        "product": product,
    }


def _open_pos_shift(db, ctx):
    from models.pos_shift import PosShift
    from utils.helpers import generate_number

    tid = ctx["tenant"].id
    number = generate_number(
        prefix="SHF",
        model=PosShift,
        field_name="shift_number",
        branch_code=ctx["branch"].id,
        tenant_id=tid,
    )
    shift = PosShift(
        tenant_id=tid,
        session_id=_ensure_session(db, ctx),
        user_id=ctx["user"].id,
        shift_number=number,
        starting_cash=Decimal("500"),
        status=PosShift.SHIFT_OPEN,
    )
    db.session.add(shift)
    db.session.flush()
    return shift


def _ensure_session(db, ctx):
    from models import PosSession
    from utils.helpers import generate_number

    tid = ctx["tenant"].id
    existing = PosSession.query.filter_by(
        tenant_id=tid,
        user_id=ctx["user"].id,
        status="open",
    ).first()
    if existing:
        return existing.id

    number = generate_number(
        prefix="POS-SES",
        model=PosSession,
        field_name="session_number",
        branch_code=ctx["branch"].id,
        tenant_id=tid,
    )
    session = PosSession(
        tenant_id=tid,
        branch_id=ctx["branch"].id,
        user_id=ctx["user"].id,
        session_number=number,
        opening_balance_cash=Decimal("500"),
        status="open",
    )
    db.session.add(session)
    db.session.flush()
    return session.id


def _process_sale(db, ctx, _shift):
    from services.sale_service import SaleService

    lines = [
        {
            "product": ctx["product"],
            "quantity": 2,
            "discount_percent": 0,
            "unit_price": 100.00,
            "serials": [],
        }
    ]

    payment_data = {
        "amount": Decimal("210"),
        "payment_method": "cash",
        "currency": "AED",
        "exchange_rate": 1.0,
    }

    sale = SaleService.create_sale(
        customer=ctx["customer"],
        seller=ctx["user"],
        lines_data=lines,
        warehouse_id=ctx["warehouse"].id,
        currency="AED",
        tax_rate=Decimal("5.00"),
        payment_data=payment_data,
    )
    db.session.flush()
    return sale


def _verify_gl(_db, ctx, sale):
    from models import GLJournalEntry
    from utils.gl_reference_types import GLRef

    entries = GLJournalEntry.query.filter_by(
        reference_type=GLRef.SALE,
        reference_id=sale.id,
        tenant_id=ctx["tenant"].id,
    ).all()

    assert entries, "No GL journal entries found for the sale"

    for entry in entries:
        total_debit = sum(Decimal(str(line.debit or 0)) for line in entry.lines)
        total_credit = sum(Decimal(str(line.credit or 0)) for line in entry.lines)
        diff = abs(total_debit - total_credit)
        assert diff <= Decimal(
            "0.001"
        ), f"Unbalanced entry {entry.entry_number}: debit={total_debit} credit={total_credit} diff={diff}"
        assert (
            entry.status == "posted"
        ), f"Entry {entry.entry_number} status is {entry.status}, expected posted"

    return entries


def _reconcile_and_close_shift(db, _ctx, shift, sale):
    from models.pos_shift import PosShift

    shift.total_sales = Decimal(str(sale.total_amount or 0))
    shift.total_cash_sales = Decimal(str(sale.paid_amount or 0))
    shift.total_card_sales = Decimal("0")
    db.session.flush()

    expected = shift.starting_cash + shift.total_cash_sales
    actual = expected
    shift.reconcile(actual, notes="E2E reconciliation")
    assert shift.status == PosShift.SHIFT_RECONCILED
    assert shift.discrepancy == Decimal(
        "0"
    ), f"Expected zero discrepancy, got {shift.discrepancy}"

    shift.close()
    assert shift.status == PosShift.SHIFT_CLOSED
    assert shift.closed_at is not None
    db.session.flush()


def _run_subscription_scheduler(_db, _ctx):
    from utils.billing_scheduler import run_subscription_check

    result = run_subscription_check()
    assert "reminded" in result
    assert "suspended" in result
    assert "active" in result

    assert (
        result["reminded"] >= 1
    ), f"Expected at least 1 reminded tenant (the E2E tenant expires in 2 days), got {result}"
    return result


def _verify_tenant_limits(db, ctx):
    from models import User, Branch
    from models.tenant import Tenant

    tid = ctx["tenant"].id
    user_count = User.query.filter_by(tenant_id=tid, is_active=True).count()
    branch_count = Branch.query.filter_by(tenant_id=tid).count()

    tenant = db.session.get(Tenant, tid)
    assert user_count <= tenant.max_users, "User count exceeds limit"
    assert branch_count <= tenant.max_branches, "Branch count exceeds limit"


def _cleanup(db, _ctx):
    from models.pos_shift import PosShift
    from models import PosSession, Sale

    db.session.query(PosShift).delete()
    db.session.query(PosSession).delete()
    db.session.query(Sale).delete()
    db.session.flush()


def run_e2e_dry_run():
    """Execute the full E2E dry-run simulation."""
    app, db = _setup()

    _failures = []

    with app.app_context():
        try:
            ctx = _seed_tenant(db)
            db.session.commit()
            logger.info("Step 1: Tenant seeded — %s", ctx["tenant"].slug)

            shift = _open_pos_shift(db, ctx)
            db.session.commit()
            assert shift.status == "open"
            logger.info(
                "Step 2: POS shift opened — %s (starting_cash=%s)",
                shift.shift_number,
                shift.starting_cash,
            )

            sale = _process_sale(db, ctx, shift)
            db.session.commit()
            assert sale.sale_number
            logger.info(
                "Step 3: Sale processed — %s (total=%s, tax=%s)",
                sale.sale_number,
                sale.total_amount,
                sale.tax_amount,
            )

            entries = _verify_gl(db, ctx, sale)
            logger.info(
                "Step 4: GL verified — %d balanced posted entries", len(entries)
            )

            _reconcile_and_close_shift(db, ctx, shift, sale)
            db.session.commit()
            logger.info(
                "Step 5: Shift reconciled & closed — discrepancy=%s", shift.discrepancy
            )

            result = _run_subscription_scheduler(db, ctx)
            logger.info("Step 6: Subscription scheduler — %s", result)

            _verify_tenant_limits(db, ctx)
            logger.info("Step 7: Tenant limits verified — OK")

            _cleanup(db, ctx)
            db.session.commit()

            print("\r\n" + "=" * 60)
            print("E2E DRY-RUN: ALL CHECKS PASSED")
            print("=" * 60)
            print(
                f"  Sale:      {sale.sale_number} (total={sale.total_amount} AED, VAT={sale.tax_amount})"
            )
            print(f"  GL entries: {len(entries)} (all balanced, all posted)")
            print(
                f"  Shift:      {shift.shift_number} (discrepancy={shift.discrepancy})"
            )
            print(
                f"  Scheduler:  reminded={result['reminded']}, suspended={result['suspended']}"
            )
            print("=" * 60)
            return 0

        except Exception as exc:
            logger.exception("E2E dry-run failed")
            print(f"\r\nE2E DRY-RUN FAILED: {exc}", file=sys.stderr)
            db.session.rollback()
            return 1


def test_e2e_dry_run():
    """pytest-compatible wrapper for the E2E dry-run."""
    rc = run_e2e_dry_run()
    assert rc == 0, "E2E dry-run did not pass all checks"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(run_e2e_dry_run())
