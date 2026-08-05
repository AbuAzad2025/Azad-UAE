"""Targeted POS <-> GL edge-case integration tests (no happy-path re-test).

Validates three financial edge cases through the REAL route stack + real DB
commits (seeding mirrors tests/integration/test_pos_e2e_journey.py::_bootstrap
which commits via db_session.commit(), so rows are visible to request sessions):

  1. POS refund (partial + full) accounting reversal: stock restoration +
     balanced, direction-correct GL reversals (Dr Sales Returns / Cr AR,
     Dr Inventory Asset / Cr COGS) and the cash-refund leg (Dr AR / Cr Cash).
  2. Split-tender + foreign-currency realignment: per-tender Payment rows each
     posting a balanced GL entry, with base-currency (AED) amounts quantized to
     0.001 and the FX rate persisted per payment; AR reconciles exactly.
  3. POS shift cash movements: Cash-In / Cash-Out posting Dr/Cr Cash vs
     Misc-Expense, with NO Revenue or Inventory accounts touched.

Default GL codes (models/gl_account_registry.py BASE_ACCOUNTS):
  1110 Cash, 1130 AR, 4100 Sales Revenue, 1140 Inventory Asset, 5100 COGS.
"""

from __future__ import annotations

import uuid
from decimal import Decimal


from extensions import db

CASH_ACCT = "1110"
AR_ACCT = "1130"
REVENUE_ACCT = "4100"
INVENTORY_ASSET_ACCT = "1140"
COGS_ACCT = "5100"


def _ensure_perm(code, category="pos"):
    from models import Permission

    perm = Permission.query.filter_by(code=code).first()
    if perm is None:
        perm = Permission(code=code, name=code, name_ar=code, category=category)
        db.session.add(perm)
        db.session.flush()
    return perm


def _bootstrap(db_session, *, qty="100", cost="10", price="50"):
    """Tenant(pro) + branch + role(cashier: sales+return+cash) + wh + product + stock.

    Commits through db_session.commit() so rows are visible to the test client's
    request sessions (the e2e helper uses the same real-commit pattern).
    """
    from models import (
        Branch,
        Product,
        ProductCategory,
        Role,
        SystemSettings,
        Tenant,
        User,
        Warehouse,
    )
    from services.stock_service import StockService

    tid = uuid.uuid4().hex[:4]
    tenant = Tenant(
        name=f"POSGL {tid}",
        name_ar=f"POSGL {tid}",
        slug=f"posgl-{tid}",
        default_currency="AED",
        subscription_plan="pro",
        enable_pos_promotions=False,
        enable_pos_multi_tender=True,
        enable_pos_shifts=True,
        enable_pos_returns=True,
    )
    db_session.add(tenant)
    db_session.flush()

    branch = Branch(tenant_id=tenant.id, name=f"Main {tid}", code=f"{tid[:4]}")
    db_session.add(branch)
    db_session.flush()

    role = Role(name=f"R {tid}", slug=f"r-{tid}", is_active=True)
    for code in ("manage_sales", "pos_return", "pos_pay_in_out"):
        role.permissions.append(_ensure_perm(code))
    db_session.add(role)
    db_session.flush()

    user = User(
        username=f"posgl-{tid}",
        email=f"posgl-{tid}@t.com",
        full_name="Cashier",
        role_id=role.id,
        tenant_id=tenant.id,
        branch_id=branch.id,
        is_active=True,
        is_owner=False,
    )
    user.set_password("x")
    db_session.add(user)
    db_session.flush()

    wh = Warehouse(
        name=f"WH {tid}",
        tenant_id=tenant.id,
        branch_id=branch.id,
        is_active=True,
        allow_negative_inventory=False,
    )
    db_session.add(wh)
    db_session.flush()

    cat = ProductCategory(name=f"Cat {tid}", tenant_id=tenant.id, is_active=True)
    db_session.add(cat)
    db_session.flush()

    product = Product(
        name=f"Item {tid}",
        sku=f"ITM-{tid}",
        tenant_id=tenant.id,
        category_id=cat.id,
        regular_price=Decimal(price),
        cost_price=Decimal(cost),
        is_active=True,
    )
    db_session.add(product)
    db_session.flush()

    StockService.add_stock(product.id, Decimal(qty), warehouse_id=wh.id)
    db_session.flush()
    if not SystemSettings.query.first():
        db_session.add(SystemSettings(enable_pos=True))
    db_session.commit()
    return {
        "tenant": tenant,
        "branch": branch,
        "user": user,
        "warehouse": wh,
        "product": product,
    }


def _login_and_open(client, username):
    client.post(
        "/auth/login",
        data={"username": username, "password": "x"},
        follow_redirects=True,
    )
    assert (
        client.post(
            "/pos/api/session/open",
            json={"opening_balance": 0},
            content_type="application/json",
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/pos/api/shift/open",
            json={"starting_cash": 0},
            content_type="application/json",
        ).status_code
        == 201
    )


def _acct(tenant_id, code):
    from models import GLAccount

    return GLAccount.query.filter_by(tenant_id=tenant_id, code=code).first()


def _entry_lines(entry):
    from models import GLJournalLine

    return GLJournalLine.query.filter_by(entry_id=entry.id).all()


def _assert_all_balanced(entries):
    for entry in entries:
        dr = sum(Decimal(str(ln.debit or 0)) for ln in _entry_lines(entry))
        cr = sum(Decimal(str(ln.credit or 0)) for ln in _entry_lines(entry))
        assert dr == cr, f"GL entry {entry.id} unbalanced: dr={dr} cr={cr}"


class TestPosRefundAccountingReversal:
    def test_partial_then_full_return_reverses_stock_and_gl(self, app, db_session, client):
        from models import (
            GLJournalEntry,
            ProductReturn,
            Sale,
            SaleLine,
        )
        from services.stock_service import StockService

        env = _bootstrap(db_session, qty="100", price="50", cost="10")
        tid = env["tenant"].id

        with app.app_context():
            from services.gl_service import GLService

            GLService.ensure_core_accounts(tid)

        with client:
            _login_and_open(client, env["user"].username)

            checkout = client.post(
                "/pos/api/checkout",
                json={
                    "lines": [
                        {
                            "product_id": env["product"].id,
                            "quantity": 4,
                            "unit_price": 50.0,
                            "discount_percent": 0,
                        }
                    ],
                    "payment_method": "cash",
                    "paid_amount": 200.0,
                    "currency": "AED",
                    "warehouse_id": env["warehouse"].id,
                },
                content_type="application/json",
            )
            assert checkout.status_code == 200, checkout.get_json()
            sale_id = checkout.get_json()["sale_id"]
            sale = db.session.get(Sale, sale_id)
            line = SaleLine.query.filter_by(sale_id=sale.id).first()

            assert StockService.get_product_stock(env["product"].id, warehouse_id=env["warehouse"].id) == Decimal("96")

            pre_entries = GLJournalEntry.query.filter_by(tenant_id=tid).count()
            revenue_code = _acct(tid, REVENUE_ACCT)
            ar_code = _acct(tid, AR_ACCT)
            inv_code = _acct(tid, INVENTORY_ASSET_ACCT)
            cogs_code = _acct(tid, COGS_ACCT)
            assert revenue_code and ar_code and inv_code and cogs_code

            # --- partial return of 2 of 4, refund_method=credit (AR credit) ---
            r1 = client.post(
                "/pos/api/returns",
                json={
                    "sale_id": sale.id,
                    "refund_method": "credit",
                    "lines": [{"sale_line_id": line.id, "quantity": 2}],
                },
                content_type="application/json",
            )
            assert r1.status_code == 201, r1.get_json()
            partial_body = r1.get_json()
            assert partial_body["success"] is True
            assert partial_body["refund_payment_number"] is None  # credit -> no cash payment

            assert StockService.get_product_stock(env["product"].id, warehouse_id=env["warehouse"].id) == Decimal("98")

            credit_entries = (
                GLJournalEntry.query.filter_by(tenant_id=tid).order_by(GLJournalEntry.id).all()[pre_entries:]
            )
            _assert_all_balanced(credit_entries)
            # Credit leg: Dr Revenue(4100) + Dr Inventory(1140) ; Cr AR(1130) + Cr COGS(5100)
            acct_codes = {ln.account.code for e in credit_entries for ln in _entry_lines(e)}
            assert REVENUE_ACCT in acct_codes
            assert AR_ACCT in acct_codes
            assert INVENTORY_ASSET_ACCT in acct_codes
            assert COGS_ACCT in acct_codes

            rev_lines = [ln for e in credit_entries for ln in _entry_lines(e) if ln.account.code == REVENUE_ACCT]
            assert all(Decimal(str(ln.debit or 0)) > 0 for ln in rev_lines)  # contra revenue debit
            assert all(Decimal(str(ln.credit or 0)) == 0 for ln in rev_lines)
            inv_lines = [
                ln for e in credit_entries for ln in _entry_lines(e) if ln.account.code == INVENTORY_ASSET_ACCT
            ]
            assert all(Decimal(str(ln.debit or 0)) > 0 for ln in inv_lines)  # inventory restored (debit)
            cogs_lines = [ln for e in credit_entries for ln in _entry_lines(e) if ln.account.code == COGS_ACCT]
            assert all(Decimal(str(ln.credit or 0)) > 0 for ln in cogs_lines)  # cogs credit
            ar_lines = [ln for e in credit_entries for ln in _entry_lines(e) if ln.account.code == AR_ACCT]
            assert all(Decimal(str(ln.credit or 0)) > 0 for ln in ar_lines)  # ar credit (customer credit)

            before_full = GLJournalEntry.query.filter_by(tenant_id=tid).count()

            # --- full return of the remaining 2, refund_method=cash ---
            r2 = client.post(
                "/pos/api/returns",
                json={
                    "sale_id": sale.id,
                    "refund_method": "cash",
                    "lines": [{"sale_line_id": line.id, "quantity": 2}],
                },
                content_type="application/json",
            )
            assert r2.status_code == 201, r2.get_json()
            assert r2.get_json()["success"] is True
            assert r2.get_json()["refund_payment_number"] is not None

            assert StockService.get_product_stock(env["product"].id, warehouse_id=env["warehouse"].id) == Decimal("100")

            new_entries = GLJournalEntry.query.filter_by(tenant_id=tid).order_by(GLJournalEntry.id).all()[before_full:]
            _assert_all_balanced(new_entries)
            # Cash-refund leg: Dr AR(1130) / Cr Cash(branch cash box, e.g. 1110-B1)
            from utils.pos_helpers import resolve_pos_cash_account_code

            cash_code = resolve_pos_cash_account_code(tid, env["branch"].id)
            assert cash_code, "no branch cash account resolved for refund"
            new_codes = {ln.account.code for e in new_entries for ln in _entry_lines(e)}
            assert AR_ACCT in new_codes and cash_code in new_codes
            ar_dr = sum(
                Decimal(str(ln.debit or 0)) for e in new_entries for ln in _entry_lines(e) if ln.account.code == AR_ACCT
            )
            cash_cr = sum(
                Decimal(str(ln.credit or 0))
                for e in new_entries
                for ln in _entry_lines(e)
                if ln.account.code == cash_code
            )
            assert ar_dr == cash_cr
            assert ar_dr == Decimal("100.000")  # full remaining value refunded in cash

            returned = ProductReturn.query.filter_by(sale_id=sale.id).order_by(ProductReturn.id).all()
            assert len(returned) == 2


class TestSplitTenderForeignCurrency:
    """Split tender (cash AED + card USD) -> balanced per-tender GL, exact AED."""

    def test_split_tender_aed_usd_reconciles_and_quantizes(self, app, db_session, client):
        from models import GLJournalEntry, Payment, Sale

        env = _bootstrap(db_session, qty="100", price="50", cost="10")
        tid = env["tenant"].id

        with app.app_context():
            from services.gl_service import GLService

            GLService.ensure_core_accounts(tid)

        with client:
            _login_and_open(client, env["user"].username)

            checkout = client.post(
                "/pos/api/checkout",
                json={
                    "lines": [
                        {
                            "product_id": env["product"].id,
                            "quantity": 1,
                            "unit_price": 50.0,
                            "discount_percent": 0,
                        }
                    ],
                    "payments": [
                        {"amount": 25.0, "payment_method": "cash", "currency": "AED", "exchange_rate": 1},
                        {"amount": 10.0, "payment_method": "card", "currency": "USD", "exchange_rate": 2.5},
                    ],
                    "currency": "AED",
                    "warehouse_id": env["warehouse"].id,
                },
                content_type="application/json",
            )
            assert checkout.status_code == 200, checkout.get_json()
            data = checkout.get_json()
            assert data["success"] is True
            sale = db.session.get(Sale, data["sale_id"])
            assert Decimal(str(sale.total_amount)) == Decimal("50.000")

            payments = Payment.query.filter_by(sale_id=sale.id).order_by(Payment.id).all()
            assert len(payments) == 2

            cash, card = payments[0], payments[1]
            assert cash.payment_method == "cash"
            assert cash.currency == "AED"
            assert Decimal(str(cash.exchange_rate)) == Decimal("1")
            assert Decimal(str(cash.amount_aed)) == Decimal("25.000")

            assert card.payment_method == "card"
            assert card.currency == "USD"
            assert Decimal(str(card.exchange_rate)) == Decimal("2.5")
            assert Decimal(str(card.amount)) == Decimal("10")
            # 10 USD * 2.5 = 25.000 AED, quantized to 0.001
            assert Decimal(str(card.amount_aed)) == Decimal("25.000")

            # Every GL entry posted for this tenant must be balanced.
            _assert_all_balanced(GLJournalEntry.query.filter_by(tenant_id=tid).all())

            # Base-currency reconciliation: AR(1130) total debit == total credit
            # (sale debits AR 50; the two tenders credit AR 25+25) -> exact AED match,
            # i.e. the foreign-currency card was realigned to 25.000 AED, no drift.
            ar_lines = [
                ln
                for e in GLJournalEntry.query.filter_by(tenant_id=tid).all()
                for ln in _entry_lines(e)
                if ln.account.code == AR_ACCT
            ]
            total_dr = sum(Decimal(str(ln.debit or 0)) for ln in ar_lines)
            total_cr = sum(Decimal(str(ln.credit or 0)) for ln in ar_lines)
            assert total_dr == total_cr == Decimal("50.000"), f"AR not reconciled: dr={total_dr} cr={total_cr}"


class TestPosShiftCashMovements:
    """Cash-In / Cash-Out post Dr/Cr Cash vs Misc-Expense; never Revenue/Inventory."""

    def test_cash_in_and_out_post_balanced_gl_without_revenue_or_inventory(self, app, db_session, client):
        from models import GLJournalEntry, PosCashMovement

        env = _bootstrap(db_session, qty="100", price="50", cost="10")
        tid = env["tenant"].id

        with app.app_context():
            from services.gl_service import GLService

            GLService.ensure_core_accounts(tid)

        with client:
            _login_and_open(client, env["user"].username)

            pay_in = client.post(
                "/pos/api/cash-movements",
                json={"type": "pay_in", "amount": 100, "reason": "opening float"},
                content_type="application/json",
            )
            assert pay_in.status_code == 201, pay_in.get_json()
            pay_in_id = pay_in.get_json()["movement"]["id"]

            pay_out = client.post(
                "/pos/api/cash-movements",
                json={"type": "pay_out", "amount": 30, "reason": "vault drop"},
                content_type="application/json",
            )
            assert pay_out.status_code == 201, pay_out.get_json()
            pay_out_id = pay_out.get_json()["movement"]["id"]

        m_in = db.session.get(PosCashMovement, pay_in_id)
        m_out = db.session.get(PosCashMovement, pay_out_id)
        assert m_in.movement_type == "pay_in"
        assert m_out.movement_type == "pay_out"
        assert Decimal(str(m_in.amount)) == Decimal("100.000")
        assert Decimal(str(m_out.amount)) == Decimal("30.000")

        for movement in (m_in, m_out):
            assert movement.gl_entry_id is not None
            entry = db.session.get(GLJournalEntry, movement.gl_entry_id)
            assert entry is not None
            _assert_all_balanced([entry])
            lines = _entry_lines(entry)
            assert len(lines) == 2
            codes = {ln.account.code for ln in lines}
            types = {ln.account.type for ln in lines}
            # Cash movement only touches liquidity (Cash) + expense (Misc) accounts.
            assert "revenue" not in types
            assert REVENUE_ACCT not in codes
            assert INVENTORY_ASSET_ACCT not in codes
            # Debit line + Credit line (one each) by non-zero side.
            has_dr = any(Decimal(str(ln.debit or 0)) > 0 for ln in lines)
            has_cr = any(Decimal(str(ln.credit or 0)) > 0 for ln in lines)
            assert has_dr and has_cr

        # pay_in: asset(Cash) debited, expense credited.
        in_lines = _entry_lines(db.session.get(GLJournalEntry, m_in.gl_entry_id))
        in_asset_dr = sum(Decimal(str(ln.debit or 0)) for ln in in_lines if ln.account.type == "asset")
        in_exp_cr = sum(Decimal(str(ln.credit or 0)) for ln in in_lines if ln.account.type == "expense")
        assert in_asset_dr == Decimal("100.000")
        assert in_exp_cr == Decimal("100.000")

        # pay_out: expense debited, asset(Cash) credited.
        out_lines = _entry_lines(db.session.get(GLJournalEntry, m_out.gl_entry_id))
        out_exp_dr = sum(Decimal(str(ln.debit or 0)) for ln in out_lines if ln.account.type == "expense")
        out_asset_cr = sum(Decimal(str(ln.credit or 0)) for ln in out_lines if ln.account.type == "asset")
        assert out_exp_dr == Decimal("30.000")
        assert out_asset_cr == Decimal("30.000")
