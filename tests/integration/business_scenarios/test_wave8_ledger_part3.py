"""Wave 8 (part 3) - the two month-end routes that landed in the ledger.

Two routes shipped into this blueprint after the LED suite was written, and
this file covers them end-to-end through the HTTP guard rather than at the
service layer: ``/ledger/fx-revaluation`` (the month-end unrealized FX
revaluation the service had no caller for) and
``/ledger/income-tax-accrual`` (the corporate-tax provision for a fiscal
year). Both run inside a transaction, both post to the ledger, and both are
behind ``manage_ledger``.

LED-118 and LED-121 pin that the guard is real. LED-119 pins the balanced
posting and the idempotency the docstring promises: a second accrual for the
same fiscal year returns the existing entry and adds nothing. LED-120 pins the
do-not-post-zero-entry rule. LED-122 walks a foreign-currency invoice through
``/ledger/fx-revaluation`` and pins that the route revalues it once, and only
once, and that the entry it posts is balanced.

The income-tax scenario pins the statutory UAE profile rather than a "some
rate": zero percent up to the threshold and 9% on the excess, which is what a
tenant with a tax decision will see.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal


def _user(client, db_session, tenant, branch, *, slug, permissions):
    from models import Permission, Role, User

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
    db_session.add(role)
    db_session.commit()

    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"{slug}-{unique}",
        email=f"{slug}-{unique}@example.com",
        full_name=f"LED {slug}",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()

    client.get("/auth/logout", follow_redirects=True)
    client.post("/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True)
    return user


class TestLED118TheIncomeTaxRouteIsGuardedByManageLedger:
    """LED-118. A viewer may read the ledger; they may not provision tax."""

    def test_a_view_ledger_only_user_is_refused(self, client, db_session, sample_tenant, sample_branch):
        _user(client, db_session, sample_tenant, sample_branch, slug="led-tax-viewer", permissions=("view_ledger",))

        resp = client.post(
            "/ledger/income-tax-accrual",
            json={"fiscal_year": 2030, "taxable_profit": "1000000"},
        )

        assert resp.status_code == 403, f"accrual answered {resp.status_code} to a user without manage_ledger"


class TestLED119TheIncomeTaxAccrualPostsBalancedOnce:
    """LED-119. The provision is one balanced entry per fiscal year."""

    def test_accrual_posts_balanced_and_second_call_adds_nothing(
        self, client, db_session, sample_tenant, sample_branch
    ):
        """LED-119. One fiscal year, one provision, Dr == Cr.

        UAE profile for the tenant: 0% up to 375,000 AED, 9% on the excess.
        A 1,000,000 profit is 625,000 over the threshold, so the provision is
        56,250 exactly - the statutory number, not a rate typed into a test.
        """
        from models import GLJournalEntry, GLJournalLine
        from utils.country_tax import compute_corporate_tax

        sample_tenant.vat_country = "AE"
        db_session.commit()

        expected = compute_corporate_tax(Decimal("1000000"), "AE")
        assert expected["tax"] == Decimal("56250.000")

        _user(
            client,
            db_session,
            sample_tenant,
            sample_branch,
            slug="led-tax-admin",
            permissions=("view_ledger", "manage_ledger"),
        )

        resp = client.post(
            "/ledger/income-tax-accrual",
            json={"fiscal_year": 2030, "taxable_profit": "1000000"},
        )
        assert resp.status_code == 200, f"accrual answered {resp.status_code}"
        payload = resp.get_json()["data"]
        assert payload["already_accrued"] is False
        assert Decimal(str(payload["tax"])) == expected["tax"]
        assert payload["entry_id"] is not None

        first_id = payload["entry_id"]
        lines = (
            db_session.query(GLJournalLine)
            .join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(GLJournalEntry.id == first_id)
            .all()
        )
        assert len(lines) == 2
        total_debit = sum(Decimal(str(ln.debit or 0)) for ln in lines)
        total_credit = sum(Decimal(str(ln.credit or 0)) for ln in lines)
        assert total_debit == total_credit == expected["tax"], (
            f"the provision entry is unbalanced: Dr {total_debit} vs Cr {total_credit}"
        )

        resp2 = client.post(
            "/ledger/income-tax-accrual",
            json={"fiscal_year": 2030, "taxable_profit": "1000000"},
        )
        assert resp2.status_code == 200, f"the second accrual answered {resp2.status_code}"
        payload2 = resp2.get_json()["data"]
        assert payload2["already_accrued"] is True, "a second accrual posted a second provision"
        from utils.gl_reference_types import GLRef

        assert (
            db_session.query(GLJournalEntry)
            .filter_by(
                tenant_id=sample_tenant.id,
                reference_type=GLRef.INCOME_TAX,
                reference_id=2030,
            )
            .count()
            == 1
        ), "the fiscal year holds more than one provision entry"


class TestLED120AZeroEstimatePostsNothing:
    """LED-120. Zero tax is not a zero entry - it is no entry at all."""

    def test_a_zero_estimate_creates_no_journal_entry(self, client, db_session, sample_tenant, sample_branch):
        from models import GLJournalEntry

        sample_tenant.vat_country = "AE"
        db_session.commit()

        _user(
            client,
            db_session,
            sample_tenant,
            sample_branch,
            slug="led-tax-zero",
            permissions=("view_ledger", "manage_ledger"),
        )

        resp = client.post(
            "/ledger/income-tax-accrual",
            json={"fiscal_year": 2031, "taxable_profit": "0"},
        )
        assert resp.status_code == 200, f"the zero accrual answered {resp.status_code}"
        payload = resp.get_json()["data"]
        assert payload["entry_id"] is None, "a zero estimate posted an empty entry"
        assert Decimal(str(payload["tax"])) == Decimal("0")
        from utils.gl_reference_types import GLRef

        assert (
            db_session.query(GLJournalEntry)
            .filter_by(
                tenant_id=sample_tenant.id,
                reference_type=GLRef.INCOME_TAX,
                reference_id=2031,
            )
            .count()
            == 0
        ), "a zero estimate left a journal entry behind"


class TestLED125TheZakatAccrualNeedsAFiscalYear:
    """LED-125. An accrual without a fiscal year is not a default year - it is
    a client error, or the idempotency key would be whatever the server
    happened to guess."""

    def test_missing_fiscal_year_is_a_400(self, client, db_session, sample_tenant, sample_branch):
        _user(
            client,
            db_session,
            sample_tenant,
            sample_branch,
            slug="led-zakat-admin",
            permissions=("view_ledger", "manage_ledger"),
        )

        resp = client.post("/ledger/zakat-accrual", json={})

        assert resp.status_code == 400, f"fiscal_year-less accrual answered {resp.status_code}"


class TestLED123TheZakatRouteIsGuardedByManageLedger:
    """LED-123. The zakat accrual posts money (Dr expense / Cr payable), so
    it sits behind ``manage_ledger``, not behind the read permission."""

    def test_a_view_ledger_only_user_is_refused(self, client, db_session, sample_tenant, sample_branch):
        _user(client, db_session, sample_tenant, sample_branch, slug="led-zakat-viewer", permissions=("view_ledger",))

        resp = client.post("/ledger/zakat-accrual", json={"fiscal_year": date.today().year})

        assert resp.status_code == 403, f"zakat accrual answered {resp.status_code} to a user without manage_ledger"


class TestLED124TheZakatAccrualPostsBalancedOnce:
    """LED-124. The accrual carries the same idempotency the income-tax route has.

    One fiscal year, one provision entry, Dr == Cr; a second POST for the same
    year returns the existing entry instead of accruing twice.
    """

    def test_second_post_for_same_year_returns_existing_entry(
        self, client, db_session, sample_tenant, sample_branch, sample_warehouse, sample_customer, sample_user
    ):
        from models import GLJournalEntry, GLJournalLine
        from services.product_service import ProductService
        from services.sale_service import SaleService
        from services.stock_service import StockService

        sample_tenant.enable_zakat = True
        db_session.add(sample_tenant)
        db_session.commit()

        _user(
            client,
            db_session,
            sample_tenant,
            sample_branch,
            slug="led-zakat-admin",
            permissions=("view_ledger", "manage_ledger"),
        )

        unique = uuid.uuid4().hex[:8]
        product = ProductService.create_product(
            name=f"Zakat LED Widget {unique}",
            sku=f"LED-ZK-{unique}",
            barcode=f"LEDZ{unique}",
            regular_price=Decimal("100"),
            cost_price=Decimal("40"),
            tenant_id=sample_tenant.id,
        )
        db_session.flush()
        StockService.add_opening_stock(product.id, Decimal("10"), warehouse_id=sample_warehouse.id)
        db_session.flush()

        # A posted receivable lifts the net working capital base above zero,
        # so the accrual has something to provision.
        SaleService.create_sale(
            customer=sample_customer,
            seller=sample_user,
            lines_data=[{"product": product, "quantity": Decimal("2"), "unit_price": Decimal("100")}],
            warehouse_id=sample_warehouse.id,
        )
        db_session.flush()
        db_session.commit()

        year = date.today().year
        resp = client.post("/ledger/zakat-accrual", json={"fiscal_year": year})
        assert resp.status_code == 200, f"zakat accrual answered {resp.status_code}"
        payload = resp.get_json()["data"]
        assert payload["entry_id"] is not None, "a positive base posted no provision"
        assert payload["zakat"] > 0, f"zakat provisioned {payload['zakat']} on a positive base"

        lines = (
            db_session.query(GLJournalLine)
            .join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(GLJournalEntry.id == payload["entry_id"])
            .all()
        )
        total_debit = sum(Decimal(str(ln.debit or 0)) for ln in lines)
        total_credit = sum(Decimal(str(ln.credit or 0)) for ln in lines)
        assert total_debit == total_credit, f"the zakat entry is unbalanced: Dr {total_debit} vs Cr {total_credit}"

        resp2 = client.post("/ledger/zakat-accrual", json={"fiscal_year": year})
        assert resp2.status_code == 200, f"the second accrual answered {resp2.status_code}"
        payload2 = resp2.get_json()["data"]
        assert payload2["already_accrued"] is True, "the same fiscal year was accrued twice"
        assert payload2["entry_id"] == payload["entry_id"], "the second call returned a different entry"

    """LED-121. Same guard shape as the tax route: view is not post."""

    def test_a_view_ledger_only_user_is_refused(self, client, db_session, sample_tenant, sample_branch):
        _user(client, db_session, sample_tenant, sample_branch, slug="led-fx-viewer", permissions=("view_ledger",))

        resp = client.post("/ledger/fx-revaluation")

        assert resp.status_code == 403, f"revaluation answered {resp.status_code} to a user without manage_ledger"
        assert resp.get_json() is None  # not an API leak: the guard fires before the handler


class TestLED122TheFxRevaluationRouteRevaluesAnOpenInvoiceOnce:
    """LED-122. The route is the caller the service never had - one sweep, one entry."""

    def test_posting_revalues_the_open_foreign_invoice_exactly_once(
        self, client, db_session, sample_tenant, sample_branch, sample_warehouse, sample_customer, sample_user
    ):
        from models import ExchangeRateRecord, GLJournalEntry, GLJournalLine
        from services.sale_service import SaleService

        _user(
            client,
            db_session,
            sample_tenant,
            sample_branch,
            slug="led-fx-admin",
            permissions=("view_ledger", "manage_ledger"),
        )

        from services.product_service import ProductService
        from services.stock_service import StockService

        unique = uuid.uuid4().hex[:8]
        product = ProductService.create_product(
            name=f"FX LED Widget {unique}",
            sku=f"LED-FX-{unique}",
            barcode=f"LEDB{unique}",
            regular_price=Decimal("100"),
            cost_price=Decimal("40"),
            tenant_id=sample_tenant.id,
        )
        db_session.flush()
        StockService.add_opening_stock(product.id, Decimal("10"), warehouse_id=sample_warehouse.id)
        db_session.flush()

        # The invoice is written at 3.50; the tracked rate moves to 3.80,
        # so the unrealized position must move accordingly. The receivable
        # is a monetary item, so it revalues at the full open balance -
        # net 350.000 plus the statutory tax billed on it (AE 5% here, so
        # the AR frozen at 3.50 is 367.500 AED), not the net only.
        SaleService.create_sale(
            customer=sample_customer,
            seller=sample_user,
            lines_data=[{"product": product, "quantity": Decimal("1"), "unit_price": Decimal("100")}],
            warehouse_id=sample_warehouse.id,
            currency="USD",
            user_exchange_rate=Decimal("3.5"),
        )
        db_session.flush()
        db_session.commit()

        for offset in (0, 1):
            db_session.add(
                ExchangeRateRecord(
                    tenant_id=sample_tenant.id,
                    from_currency="USD",
                    to_currency="AED",
                    rate=Decimal("3.8"),
                    source="manual",
                    effective_date=date.today() + timedelta(days=offset),
                )
            )
        db_session.commit()

        resp = client.post("/ledger/fx-revaluation")
        assert resp.status_code == 200, f"revaluation answered {resp.status_code}"
        payload = resp.get_json()["data"]
        assert payload["errors"] == [], f"revaluation reported {payload['errors']}"
        assert payload["ar_count"] == 1, f"expected one revalued receivable, got {payload['ar_count']}"
        assert payload["skipped_existing_period"] is False
        assert payload["entry_ids"], "the revaluation posted no entry"

        lines = (
            db_session.query(GLJournalLine)
            .join(GLJournalEntry, GLJournalLine.entry_id == GLJournalEntry.id)
            .filter(GLJournalEntry.id.in_(payload["entry_ids"]))
            .all()
        )
        total_debit = sum(Decimal(str(ln.debit or 0)) for ln in lines)
        total_credit = sum(Decimal(str(ln.credit or 0)) for ln in lines)
        assert total_debit == total_credit, (
            f"the revaluation entry is unbalanced: Dr {total_debit} vs Cr {total_credit}"
        )
        # open AR 367.500 frozen at 3.50 / 105 USD x 3.80 = 399.000 -> diff 31.500
        assert total_debit == Decimal("31.500")

        # Sweep again: the period already holds a live revaluation entry, so
        # the route must skip rather than double-count.
        resp2 = client.post("/ledger/fx-revaluation")
        assert resp2.status_code == 200, f"the second revaluation answered {resp2.status_code}"
        payload2 = resp2.get_json()["data"]
        assert payload2["skipped_existing_period"] is True, "the same month was revalued twice"
        assert payload2["ar_count"] == 0
