"""سيناريوهات مالية شاملة لكشوفات حسابات الجهات (زبون/مورد/شريك/موظف) ودفتر الأستاذ.

تغطي القواعد الحرجة:
- الرصيد الافتتاحي يُحسب من حركات ما قبل الفترة (وليس صفرًا).
- الرصيد الختامي للفترة المحددة يساوي الرصيد بدون تحديد فترة (لا فقدان للتاريخ).
- المرتجعات المعتمدة تظهر كدائن وتقلل الذمة.
- الدفعات المرفوضة (شيكات مرتدة) لا تؤثر على الرصيد، بينما الشيك المعلق
  يؤثر فوراً (قيد الاستلام Dr شيكات تحت التحصيل / Cr ذمم يخفض الذمة).
- GL: الرصيد الافتتاحي للقيود المرحلة فقط، ولا مضاعفة عند غياب date_from.
- الموظف: السلفة المخصومة من الراتب لا تُحسب مرتين.
- الشريك: عزل tenant صارم.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from extensions import db


# ───────────────────────── helpers ─────────────────────────


def _sale(tenant_id, customer_id, seller_id, number, amount, when):
    from models import Sale

    s = Sale(
        tenant_id=tenant_id,
        sale_number=number,
        customer_id=customer_id,
        seller_id=seller_id,
        sale_date=when,
        subtotal=Decimal(str(amount)),
        total_amount=Decimal(str(amount)),
        amount=Decimal(str(amount)),
        amount_aed=Decimal(str(amount)),
        balance_due=Decimal(str(amount)),
        currency="AED",
        status="confirmed",
    )
    db.session.add(s)
    db.session.flush()
    return s


def _payment(
    tenant_id,
    number,
    amount,
    when,
    *,
    customer_id=None,
    supplier_id=None,
    direction="incoming",
    confirmed=True,
    method="cash",
    user_id=None,
):
    from models import Payment

    p = Payment(
        tenant_id=tenant_id,
        payment_number=number,
        payment_type="payment",
        direction=direction,
        customer_id=customer_id,
        supplier_id=supplier_id,
        amount=Decimal(str(amount)),
        amount_aed=Decimal(str(amount)),
        currency="AED",
        exchange_rate=Decimal("1"),
        payment_method=method,
        payment_confirmed=confirmed,
        payment_date=when,
        user_id=user_id,
    )
    db.session.add(p)
    db.session.flush()
    return p


def _sale_return(tenant_id, sale, number, amount, when, *, status="approved"):
    from models import ProductReturn

    r = ProductReturn(
        tenant_id=tenant_id,
        return_number=number,
        sale_id=sale.id,
        customer_id=sale.customer_id,
        return_date=when,
        total_amount=Decimal(str(amount)),
        refund_amount=Decimal(str(amount)),
        amount_aed=Decimal(str(amount)),
        currency="AED",
        exchange_rate=Decimal("1"),
        status=status,
    )
    db.session.add(r)
    db.session.flush()
    return r


def _purchase(tenant_id, supplier_id, user_id, number, amount, when):
    from models import Purchase

    p = Purchase(
        tenant_id=tenant_id,
        purchase_number=number,
        supplier_id=supplier_id,
        supplier_name="Test Supplier",
        purchase_date=when,
        user_id=user_id,
        subtotal=Decimal(str(amount)),
        total_amount=Decimal(str(amount)),
        amount=Decimal(str(amount)),
        amount_aed=Decimal(str(amount)),
        currency="AED",
        status="confirmed",
    )
    db.session.add(p)
    db.session.flush()
    return p


def _purchase_return(tenant_id, purchase, number, amount, when):
    from models import PurchaseReturn

    r = PurchaseReturn(
        tenant_id=tenant_id,
        return_number=number,
        purchase_id=purchase.id,
        supplier_id=purchase.supplier_id,
        return_date=when,
        subtotal=Decimal(str(amount)),
        total_amount=Decimal(str(amount)),
        amount_aed=Decimal(str(amount)),
        currency="AED",
        exchange_rate=Decimal("1"),
    )
    db.session.add(r)
    db.session.flush()
    return r


def _final_balance_from_html(html):
    """استخراج الرصيد الختامي من صف الكشف النهائي."""
    import re

    m = re.findall(r"final-balance-row[\s\S]*?([-\d,]+\.\d+)", html)
    assert m, "final balance row not found in statement HTML"
    return float(m[-1].replace(",", ""))


# ───────────────────── customer statement ─────────────────────


class TestCustomerStatement:
    def _seed(self, db_session, sample_tenant, sample_customer, sample_user):
        tid = sample_tenant.id
        cid = sample_customer.id
        uid = sample_user.id
        # قبل الفترة
        s_old = _sale(tid, cid, uid, "SAL-OLD-1", 500, datetime(2026, 4, 10, tzinfo=timezone.utc))
        _payment(
            tid,
            "PAY-OLD-1",
            200,
            datetime(2026, 4, 15, tzinfo=timezone.utc),
            customer_id=cid,
            direction="incoming",
            user_id=uid,
        )
        # داخل الفترة
        s_new = _sale(tid, cid, uid, "SAL-NEW-1", 1000, datetime(2026, 5, 10, tzinfo=timezone.utc))
        _payment(
            tid,
            "PAY-NEW-1",
            400,
            datetime(2026, 5, 15, tzinfo=timezone.utc),
            customer_id=cid,
            direction="incoming",
            user_id=uid,
        )
        _sale_return(tid, s_new, "RET-NEW-1", 150, datetime(2026, 5, 20, tzinfo=timezone.utc))
        # مرتجع مرفوض — لا أثر له
        _sale_return(tid, s_new, "RET-REJ-1", 999, datetime(2026, 5, 21, tzinfo=timezone.utc), status="rejected")
        # شيك وارد معلق — يؤثر فوراً (قيد الاستلام Dr CUC / Cr AR يخفض الذمة)
        _payment(
            tid,
            "PAY-PEND-1",
            777,
            datetime(2026, 5, 22, tzinfo=timezone.utc),
            customer_id=cid,
            direction="incoming",
            confirmed=False,
            method="cheque",
            user_id=uid,
        )
        db_session.commit()
        return s_old

    def test_full_history_balance(self, db_session, auth_client, sample_tenant, sample_customer, sample_user):
        self._seed(db_session, sample_tenant, sample_customer, sample_user)
        resp = auth_client.get(f"/customers/{sample_customer.id}/statement")
        assert resp.status_code == 200
        # دائن: 200 + 400 + 150 + 777 (شيك معلق) = 1527 | مدين: 500 + 1000 = 1500 → 27
        assert _final_balance_from_html(resp.get_data(as_text=True)) == pytest.approx(27.0)

    def test_opening_balance_and_period_consistency(
        self, db_session, auth_client, sample_tenant, sample_customer, sample_user
    ):
        self._seed(db_session, sample_tenant, sample_customer, sample_user)
        resp = auth_client.get(f"/customers/{sample_customer.id}/statement?date_from=2026-05-01&date_to=2026-05-31")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # الافتتاحي: 200 دفع - 500 بيع = -300
        assert "الرصيد الافتتاحي" in html
        assert _final_balance_from_html(html) == pytest.approx(27.0)

    def test_rejected_return_excluded_and_pending_cheque_included(
        self, db_session, auth_client, sample_tenant, sample_customer, sample_user
    ):
        tid = sample_tenant.id
        cid = sample_customer.id
        uid = sample_user.id
        s = _sale(tid, cid, uid, "SAL-X-1", 300, datetime(2026, 5, 5, tzinfo=timezone.utc))
        _sale_return(tid, s, "RET-X-REJ", 100, datetime(2026, 5, 6, tzinfo=timezone.utc), status="rejected")
        _payment(
            tid,
            "PAY-X-CHQ",
            120,
            datetime(2026, 5, 7, tzinfo=timezone.utc),
            customer_id=cid,
            confirmed=False,
            method="cheque",
            user_id=uid,
        )
        db_session.commit()
        resp = auth_client.get(f"/customers/{cid}/statement")
        assert resp.status_code == 200
        # البيع 300 مدين - شيك معلق 120 دائن → -180 (المرتجع المرفوض لا أثر له)
        assert _final_balance_from_html(resp.get_data(as_text=True)) == pytest.approx(-180.0)


# ───────────────────── supplier statement ─────────────────────


class TestSupplierStatement:
    def _seed(self, db_session, sample_tenant, sample_supplier, sample_user):
        tid = sample_tenant.id
        sid = sample_supplier.id
        uid = sample_user.id
        p_old = _purchase(tid, sid, uid, "PUR-OLD-1", 800, datetime(2026, 4, 5, tzinfo=timezone.utc))
        _payment(
            tid,
            "SPAY-OLD-1",
            300,
            datetime(2026, 4, 10, tzinfo=timezone.utc),
            supplier_id=sid,
            direction="outgoing",
            user_id=uid,
        )
        p_new = _purchase(tid, sid, uid, "PUR-NEW-1", 600, datetime(2026, 5, 5, tzinfo=timezone.utc))
        _purchase_return(tid, p_new, "PRET-NEW-1", 100, datetime(2026, 5, 8, tzinfo=timezone.utc))
        db_session.commit()
        return p_old

    def test_supplier_balance_with_returns(self, db_session, auth_client, sample_tenant, sample_supplier, sample_user):
        self._seed(db_session, sample_tenant, sample_supplier, sample_user)
        resp = auth_client.get(f"/suppliers/{sample_supplier.id}/statement")
        assert resp.status_code == 200
        # مدين: 800 + 600 | دائن: 300 دفع + 100 مرتجع → 1000
        assert _final_balance_from_html(resp.get_data(as_text=True)) == pytest.approx(1000.0)

    def test_supplier_opening_balance(self, db_session, auth_client, sample_tenant, sample_supplier, sample_user):
        self._seed(db_session, sample_tenant, sample_supplier, sample_user)
        resp = auth_client.get(f"/suppliers/{sample_supplier.id}/statement?date_from=2026-05-01&date_to=2026-05-31")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # الافتتاحي: 800 - 300 = 500 | الفترة: +600 -100 → 1000
        assert "الرصيد الافتتاحي" in html
        assert _final_balance_from_html(html) == pytest.approx(1000.0)


# ───────────────────── GL account statement ─────────────────────


def _balanced_lines(amount):
    return [
        {"account": "1111", "debit": Decimal(str(amount)), "credit": Decimal("0"), "description": "cash"},
        {"account": "4101", "debit": Decimal("0"), "credit": Decimal(str(amount)), "description": "revenue"},
    ]


def _post_entry(entry_id, *, user_id=1):
    from services.advanced_journal_manager import AdvancedJournalEntryManager

    AdvancedJournalEntryManager.validate_entry(entry_id=entry_id, validated_by=user_id, commit=False)
    AdvancedJournalEntryManager.post_entry(entry_id=entry_id, posted_by=user_id, commit=False)
    db.session.flush()


class TestGLStatement:
    def test_opening_counts_posted_only(self, db_session, sample_tenant, sample_gl_accounts, mocker):
        from services.gl_service import GLService
        from models import GLAccount

        mocker.patch("services.gl_helpers.assert_period_open")
        tid = sample_tenant.id
        cash = GLAccount.query.filter_by(tenant_id=tid, code="1111").first()

        posted_old = GLService.create_journal_entry(
            datetime(2026, 4, 10, tzinfo=timezone.utc), "posted old", _balanced_lines(200), tenant_id=tid
        )
        _post_entry(posted_old.id)
        # مسودة قبل الفترة — يجب ألا تدخل الرصيد الافتتاحي
        GLService.create_journal_entry(
            datetime(2026, 4, 15, tzinfo=timezone.utc), "draft old", _balanced_lines(999), tenant_id=tid
        )
        posted_new = GLService.create_journal_entry(
            datetime(2026, 5, 5, tzinfo=timezone.utc), "posted new", _balanced_lines(150), tenant_id=tid
        )
        _post_entry(posted_new.id)
        db_session.commit()

        stmt = GLService.get_account_statement(
            cash.id, date_from=date(2026, 5, 1), date_to=date(2026, 5, 31), tenant_id=tid
        )
        assert stmt["opening_balance"] == pytest.approx(200.0)
        assert stmt["closing_balance"] == pytest.approx(350.0)
        assert len(stmt["transactions"]) == 1

    def test_no_date_from_no_doubling(self, db_session, sample_tenant, sample_gl_accounts, mocker):
        from services.gl_service import GLService
        from models import GLAccount

        mocker.patch("services.gl_helpers.assert_period_open")
        tid = sample_tenant.id
        cash = GLAccount.query.filter_by(tenant_id=tid, code="1111").first()
        entry = GLService.create_journal_entry(
            datetime(2026, 6, 10, tzinfo=timezone.utc), "no doubling", _balanced_lines(500), tenant_id=tid
        )
        _post_entry(entry.id)
        db_session.commit()

        stmt = GLService.get_account_statement(cash.id, tenant_id=tid)
        # بدون date_from: الافتتاحي صفر والختامي = مجموع الحركات مرة واحدة فقط
        assert stmt["opening_balance"] == pytest.approx(0.0)
        assert stmt["closing_balance"] == pytest.approx(500.0)

    def test_same_day_deterministic_order(self, db_session, sample_tenant, sample_gl_accounts, mocker):
        from services.gl_service import GLService
        from models import GLAccount

        mocker.patch("services.gl_helpers.assert_period_open")
        tid = sample_tenant.id
        cash = GLAccount.query.filter_by(tenant_id=tid, code="1111").first()
        same_day = datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc)
        ids = []
        for amt in (100, 50, 25):
            e = GLService.create_journal_entry(same_day, f"e{amt}", _balanced_lines(amt), tenant_id=tid)
            _post_entry(e.id)
            ids.append(e.id)
        db_session.commit()

        stmt1 = GLService.get_account_statement(cash.id, tenant_id=tid)
        stmt2 = GLService.get_account_statement(cash.id, tenant_id=tid)
        seq1 = [t["entry_id"] for t in stmt1["transactions"]]
        seq2 = [t["entry_id"] for t in stmt2["transactions"]]
        assert seq1 == seq2 == sorted(ids)
        assert stmt1["closing_balance"] == pytest.approx(175.0)


# ───────────────────── payroll statement ─────────────────────


class TestPayrollStatement:
    def test_advance_deduction_not_double_counted(self, db_session, auth_client, sample_tenant, sample_employee):
        from models import SalaryAdvance, PayrollTransaction

        tid = sample_tenant.id
        eid = sample_employee.id
        adv = SalaryAdvance(
            tenant_id=tid,
            employee_id=eid,
            amount=Decimal("1000"),
            total_amount=Decimal("1000"),
            deducted_amount=Decimal("400"),
            remaining_amount=Decimal("600"),
            date=date(2026, 4, 1),
            description="سلفة تجريبية",
            status="approved",
            created_by=1,
        )
        pt = PayrollTransaction(
            tenant_id=tid,
            employee_id=eid,
            month=5,
            year=2026,
            basic_amount=Decimal("5000"),
            net_salary=Decimal("4600"),  # 5000 - 400 خصم سلفة
            payment_date=date(2026, 5, 31),
        )
        db_session.add_all([adv, pt])
        db_session.commit()

        resp = auth_client.get(f"/payroll/statement/{eid}")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # قيد سداد السلفة الموجب يجب أن يظهر وإلا احتُسب الخصم مرتين
        assert "سداد سلفة" in html
        # استخراج المبالغ من خلايا العرض: -1000 (سلفة) + 400 (سداد) + 4600 (راتب)
        import re

        cells = re.findall(r'dir="ltr">\s*<span class="text-(?:danger|success)">([+-]?[\d.]+)</span>', html)
        assert len(cells) == 3
        assert sum(float(c) for c in cells) == pytest.approx(4000.0)


# ───────────────────── partner statement ─────────────────────


class TestPartnerStatement:
    def test_tenant_isolation(self, db_session, sample_tenant):
        import uuid

        from models import Partner, PartnerTransaction, Tenant
        from services.partner_service import PartnerService

        partner = Partner(
            tenant_id=sample_tenant.id,
            code="P1",
            name="شريك اختبار",
            share_percentage=Decimal("50"),
            current_balance=Decimal("0"),
        )
        db_session.add(partner)
        db_session.flush()
        # tenant ثانٍ حقيقي (قيود FK تمنع المعرفات الوهمية)
        other_tenant = Tenant(
            name=f"Other Co {uuid.uuid4().hex[:8]}",
            name_ar="شركة أخرى",
            slug=f"other-co-{uuid.uuid4().hex[:8]}",
            email=f"other-{uuid.uuid4().hex[:8]}@example.com",
            country="AE",
            subscription_plan="basic",
        )
        db_session.add(other_tenant)
        db_session.flush()
        tx_ok = PartnerTransaction(
            tenant_id=sample_tenant.id,
            partner_id=partner.id,
            transaction_type="profit_share",
            amount=Decimal("1000"),
            amount_base=Decimal("1000"),
            balance_after=Decimal("1000"),
            transaction_date=date(2026, 5, 10),
        )
        # حركة بمعرّف tenant آخر — يجب استبعادها دائمًا
        tx_bad = PartnerTransaction(
            tenant_id=other_tenant.id,
            partner_id=partner.id,
            transaction_type="withdrawal",
            amount=Decimal("-500"),
            amount_base=Decimal("-500"),
            balance_after=Decimal("500"),
            transaction_date=date(2026, 5, 11),
        )
        db_session.add_all([tx_ok, tx_bad])
        db_session.commit()

        stmt = PartnerService.get_partner_statement(partner.id, date(2026, 5, 1), date(2026, 5, 31))
        assert len(stmt["transactions"]) == 1
        assert stmt["closing_balance"] == pytest.approx(1000.0)
