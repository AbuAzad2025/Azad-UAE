"""Deep behavioral coverage for models/gl.py against the real schema."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from extensions import db
from models.gl import (
    GLAccount,
    GLAccountMapping,
    GLJournalEntry,
    GLJournalLine,
)
from services.gl_posting import UnbalancedJournalEntryError


def _acct(tenant_id, code, name, *, type_="asset", sub_type=None, is_header=False, parent=None, is_active=True):
    return GLAccount(
        tenant_id=tenant_id,
        code=code,
        name=name,
        name_ar=None,
        type=type_,
        sub_type=sub_type,
        is_header=is_header,
        parent=parent,
        is_active=is_active,
    )


@pytest.fixture
def chart(db_session, sample_tenant):
    """Cash header + two leaf children + an untyped leaf."""
    cash_header = _acct(sample_tenant.id, "1000", "Cash", is_header=True)
    bank = _acct(sample_tenant.id, "1010", "Bank", sub_type="bank")
    till = _acct(sample_tenant.id, "1020", "Till", sub_type="cash")
    off = _acct(sample_tenant.id, "1030", "ClosedLeaf", is_active=False)
    cash_header.children.extend([bank, till, off])
    rev = _acct(sample_tenant.id, "4000", "Revenue", type_="revenue")
    j1 = _acct(sample_tenant.id, "1050", "AbsorbA")
    j2 = _acct(sample_tenant.id, "1060", "AbsorbB")
    db.session.add_all([cash_header, bank, till, off, rev, j1, j2])
    db.session.flush()
    return {"header": cash_header, "bank": bank, "till": till, "off": off, "rev": rev, "j1": j1, "j2": j2}


def _post_legs(tenant_id, legs):
    """Post one balanced entry composed of (account, debit, credit) lines."""
    total_d = sum((Decimal(d) for _, d, _ in legs), Decimal("0"))
    total_c = sum((Decimal(c) for _, _, c in legs), Decimal("0"))
    assert total_d == total_c, "probe entries must be balanced"
    entry = GLJournalEntry(
        tenant_id=tenant_id,
        entry_number=f"LEGS-{total_d}-{total_c}-{datetime.now(UTC).timestamp()}",
        description="probe",
        reference_type="manual",
        status="posted",
        total_debit=total_d,
        total_credit=total_c,
        entry_date=datetime.now(UTC),
    )
    db.session.add(entry)
    db.session.flush()
    for account, debit, credit in legs:
        db.session.add(
            GLJournalLine(
                tenant_id=tenant_id,
                entry_id=entry.id,
                account_id=account.id,
                debit=Decimal(debit),
                credit=Decimal(credit),
            )
        )
    db.session.flush()
    return entry


class TestGLAccountBalance:
    def test_leaf_balance_sign_conventions(self, db_session, sample_tenant, chart):
        # Bank receives +50 then loses 60 ⇒ final net −10 (asset = debit − credit)
        _post_legs(sample_tenant.id, [(chart["bank"], 50, 0), (chart["j1"], 0, 30), (chart["j2"], 0, 20)])
        assert chart["bank"].get_balance() == Decimal("50")
        _post_legs(sample_tenant.id, [(chart["j1"], 40, 0), (chart["j2"], 20, 0), (chart["bank"], 0, 60)])
        assert chart["bank"].get_balance() == Decimal("-10")

        # Revenue flips the sign (credit − debit)
        _post_legs(sample_tenant.id, [(chart["rev"], 0, 12), (chart["j1"], 8, 0), (chart["j2"], 4, 0)])
        assert chart["rev"].get_balance() == Decimal("12")
        _post_legs(sample_tenant.id, [(chart["rev"], 2, 0), (chart["j1"], 0, 2)])
        assert chart["rev"].get_balance() == Decimal("10")


class TestGLAccountProperties:
    def test_full_name_prefers_arabic(self, sample_tenant):
        acct = _acct(sample_tenant.id, "1110", "Cash")
        acct.name_ar = "النقدية"
        assert acct.full_name == "1110 - النقدية"
        acct.name_ar = None
        assert acct.full_name == "1110 - Cash"

    @pytest.mark.parametrize(
        ("type_", "expected"),
        [
            ("asset", "أصول"),
            ("liability", "خصوم"),
            ("equity", "حقوق ملكية"),
            ("revenue", "إيرادات"),
            ("expense", "مصروفات"),
            ("weird", "weird"),
        ],
    )
    def test_type_ar_matrix(self, sample_tenant, type_, expected):
        assert _acct(sample_tenant.id, "9", "x", type_=type_).type_ar == expected

    @pytest.mark.parametrize(
        ("sub_type", "expected"),
        [
            ("receivable", "ذمم مدينة"),
            ("payable", "ذمم دائنة"),
            ("inventory", "مخزون"),
            ("fixed_asset", "أصل ثابت"),
            ("cogs", "تكلفة بضاعة"),
            ("vat", "ضريبة قيمة مضافة"),
            ("unknown-x", "unknown-x"),
            (None, ""),
        ],
    )
    def test_sub_type_ar_matrix(self, sample_tenant, sub_type, expected):
        assert _acct(sample_tenant.id, "9", "x", sub_type=sub_type).sub_type_ar == expected

    def test_reprs(self, sample_tenant):
        assert "GLAccount" in repr(_acct(sample_tenant.id, "55", "Thing"))


class TestGLAccountBalanceExtras:
    def test_draft_entries_excluded(self, db_session, sample_tenant, chart):
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="DRAFTONLY",
            status="draft",
            total_debit=Decimal("40"),
            total_credit=Decimal("40"),
        )
        db.session.add(entry)
        db.session.flush()
        db.session.add(
            GLJournalLine(
                tenant_id=sample_tenant.id,
                entry_id=entry.id,
                account_id=chart["till"].id,
                debit=Decimal("40"),
                credit=Decimal("40"),
            )
        )
        db.session.flush()
        assert chart["till"].get_balance() == Decimal("0")

    def test_date_filters(self, db_session, sample_tenant, chart):
        old_entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="OLDDATE",
            status="posted",
            total_debit=Decimal("7"),
            total_credit=Decimal("7"),
            entry_date=datetime(2020, 1, 1, tzinfo=UTC),
        )
        db.session.add(old_entry)
        db.session.flush()
        db.session.add(
            GLJournalLine(tenant_id=sample_tenant.id, entry_id=old_entry.id, account_id=chart["till"].id, debit=7)
        )
        new_entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="NEWDATE",
            status="posted",
            total_debit=Decimal("3"),
            total_credit=Decimal("3"),
            entry_date=datetime.now(UTC),
        )
        db.session.add(new_entry)
        db.session.flush()
        db.session.add(
            GLJournalLine(tenant_id=sample_tenant.id, entry_id=new_entry.id, account_id=chart["till"].id, debit=3)
        )

        since = datetime(2024, 1, 1, tzinfo=UTC)
        assert chart["till"].get_balance(start_date=since) == Decimal("3")
        assert chart["till"].get_balance(as_of_date=datetime(2021, 1, 1, tzinfo=UTC)) == Decimal("7")

    def test_header_aggregates_active_children_only(self, db_session, sample_tenant, chart):
        # Balanced entry spanning header children (bank +33, till −18) plus an
        # inactive leaf leg that must never leak into the parent rollup.
        _post_legs(
            sample_tenant.id,
            [(chart["bank"], 33, 0), (chart["till"], 0, 18), (chart["off"], 0, 15)],
        )
        assert chart["bank"].get_balance() == Decimal("33")
        assert chart["header"].get_balance() == Decimal("15")

    def test_recursion_guards(self, db_session, sample_tenant, chart):
        header = chart["header"]
        with pytest.raises(RecursionError):
            header.get_balance(_depth=11)
        with pytest.raises(ValueError, match="Circular"):
            header.get_balance(_visited={id(header)})
        with pytest.raises(RecursionError):
            header.get_children_recursive(max_depth=1, _depth=2)
        with pytest.raises(ValueError, match="Circular"):
            header.get_children_recursive(_visited={id(header)})


class TestGLAccountChildrenRecursive:
    def test_collects_nested_descendants(self, db_session, sample_tenant):
        root = _acct(sample_tenant.id, "2000", "Root", is_header=True)
        mid = _acct(sample_tenant.id, "2010", "Mid", is_header=True)
        leaf = _acct(sample_tenant.id, "2011", "Leaf")
        mid.children.append(leaf)
        root.children.append(mid)
        db.session.add_all([root, mid, leaf])
        db.session.flush()
        ids = {a.id for a in root.get_children_recursive()}
        assert ids == {mid.id, leaf.id}


class TestGLJournalEntry:
    def _balanced(self, tenant_id, number="REV-1"):
        return GLJournalEntry(
            tenant_id=tenant_id,
            entry_number=number,
            description="original",
            status="posted",
            total_debit=Decimal("50"),
            total_credit=Decimal("50"),
        )

    def test_repr_and_type_ar(self, sample_tenant):
        e = self._balanced(sample_tenant.id)
        assert "<GLEntry" in repr(e)
        e.entry_type = "manual"
        assert e.entry_type_ar == "قيد يدوي"
        e.entry_type = "closing"
        assert e.entry_type_ar == "قيد إقفال"
        e.entry_type = "mystery"
        assert e.entry_type_ar == "mystery"

    def test_is_balanced_threshold(self, sample_tenant):
        e = self._balanced(sample_tenant.id)
        assert e.is_balanced() is True
        e.total_credit = Decimal("50.0009")
        assert e.is_balanced() is True
        e.total_credit = Decimal("49")
        assert e.is_balanced() is False

    def test_reverse_entry_creates_mirror(self, db_session, sample_tenant, chart):
        entry = self._balanced(sample_tenant.id, number="ORIG-1")
        db.session.add(entry)
        db.session.flush()
        db.session.add(
            GLJournalLine(
                tenant_id=sample_tenant.id,
                entry_id=entry.id,
                account_id=chart["bank"].id,
                debit=Decimal("50"),
                credit=Decimal("0"),
                amount=Decimal("50"),
                amount_aed=Decimal("50"),
            )
        )
        db.session.flush()

        mirror = entry.reverse_entry(description="undo it")
        assert mirror.reversed_entry_id == entry.id
        assert mirror.status == "posted"
        assert mirror.total_debit == Decimal("50")
        line = mirror.lines[0]
        assert line.debit == Decimal("0") and line.credit == Decimal("50")
        assert line.amount_aed == Decimal("-50")
        assert entry.is_reversed is True

        with pytest.raises(ValueError, match="عكسه مسبقاً"):
            entry.reverse_entry()

    def test_base_amount_alias(self, sample_tenant):
        line = GLJournalLine(amount_aed=Decimal("15"))
        assert line.base_amount == Decimal("15")
        line.base_amount = Decimal("18")
        assert line.amount_aed == Decimal("18")

    def test_line_repr(self, sample_tenant):
        line = GLJournalLine(account_id=3, debit=Decimal("1"), credit=Decimal("2"))
        assert "acc=3" in repr(line)


class TestGLEntryListener:
    def test_unbalanced_insert_rejected(self, db_session, sample_tenant):
        bad = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="BAD-1",
            total_debit=Decimal("100"),
            total_credit=Decimal("90"),
            status="draft",
        )
        db.session.add(bad)
        with pytest.raises(UnbalancedJournalEntryError):
            db.session.flush()

    def test_status_sync_flags(self, db_session, sample_tenant):
        posted = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="SYNC-P",
            total_debit=Decimal("1"),
            total_credit=Decimal("1"),
            status="posted",
        )
        db.session.add(posted)
        db.session.flush()
        assert posted.is_posted is True

        draft = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="SYNC-D",
            total_debit=Decimal("1"),
            total_credit=Decimal("1"),
            status="draft",
        )
        db.session.add(draft)
        db.session.flush()
        assert draft.is_posted is False


class TestGLAccountMappingValidation:
    def test_valid_concept_passes_silently(self):
        GLAccountMapping.validate_concept_code("CASH")

    def test_unknown_concept_raises_with_registry(self):
        with pytest.raises(ValueError, match="Unknown GL concept"):
            GLAccountMapping.validate_concept_code("NOT_A_REAL_CONCEPT_XYZ")
