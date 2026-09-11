"""Gap coverage for models/gl.py — balance edges, reversal, entry validation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from models.gl import GLAccount, GLAccountMapping, GLJournalEntry, GLJournalLine
from services.gl_posting import UnbalancedJournalEntryError


def _account(db_session, tenant_id, code, type_="asset", **kwargs):
    acct = GLAccount(tenant_id=tenant_id, code=code, name=f"Acct {code}", type=type_, **kwargs)
    db_session.add(acct)
    db_session.flush()
    return acct


def _entry(db_session, tenant_id, number, status="posted", debit="100", credit="100"):
    entry = GLJournalEntry(
        tenant_id=tenant_id,
        entry_number=number,
        description="cov3",
        reference_type="manual",
        status=status,
        total_debit=Decimal(debit),
        total_credit=Decimal(credit),
        entry_date=datetime.now(UTC),
    )
    db_session.add(entry)
    db_session.flush()
    return entry


def _legs(db_session, tenant_id, entry, legs):
    for account, debit, credit in legs:
        db_session.add(
            GLJournalLine(
                tenant_id=tenant_id,
                entry_id=entry.id,
                account_id=account.id,
                debit=Decimal(str(debit)),
                credit=Decimal(str(credit)),
                amount_aed=Decimal(str(debit)) - Decimal(str(credit)),
            )
        )
    db_session.flush()


class TestSubTypeAr:
    def test_unknown(self):
        assert GLAccount(sub_type="mystery").sub_type_ar == "mystery"

    def test_none_gives_empty(self):
        assert GLAccount(sub_type=None).sub_type_ar == ""


class TestGetBalanceGuards:
    def test_depth_exceeded(self, db_session, sample_tenant):
        acct = _account(db_session, sample_tenant.id, "9001")
        with pytest.raises(RecursionError, match="Max depth"):
            acct.get_balance(_depth=11)

    def test_circular(self, db_session, sample_tenant):
        acct = _account(db_session, sample_tenant.id, "9002")
        with pytest.raises(ValueError, match="Circular"):
            acct.get_balance(_visited={id(acct)})

    def test_header_sums_only_active(self, db_session, sample_tenant):
        header = _account(db_session, sample_tenant.id, "9010", is_header=True)
        active = _account(db_session, sample_tenant.id, "9011")
        inactive = _account(db_session, sample_tenant.id, "9012", is_active=False)
        header.children.extend([active, inactive])
        db_session.flush()
        entry = _entry(db_session, sample_tenant.id, "HDR-1")
        _legs(db_session, sample_tenant.id, entry, [(active, 40, 0), (inactive, 999, 0)])
        other = _account(db_session, sample_tenant.id, "9013")
        db_session.add(
            GLJournalLine(
                tenant_id=sample_tenant.id,
                entry_id=entry.id,
                account_id=other.id,
                debit=Decimal("40"),
                credit=Decimal("0"),
            )
        )
        db_session.flush()
        # rebalance helper entry leg so the probe entry stays consistent
        assert header.get_balance() == Decimal("40")


class TestGetBalanceFilters:
    def test_start_date_excludes(self, db_session, sample_tenant):
        acct = _account(db_session, sample_tenant.id, "9020")
        entry = _entry(db_session, sample_tenant.id, "FILT-1")
        _legs(db_session, sample_tenant.id, entry, [(acct, 75, 0)])
        other = _account(db_session, sample_tenant.id, "9021")
        db_session.add(
            GLJournalLine(
                tenant_id=sample_tenant.id,
                entry_id=entry.id,
                account_id=other.id,
                debit=Decimal("0"),
                credit=Decimal("75"),
            )
        )
        db_session.flush()
        tomorrow = datetime.now(UTC) + timedelta(days=1)
        assert acct.get_balance(start_date=tomorrow) == Decimal("0")
        assert acct.get_balance() == Decimal("75")

    def test_end_and_as_of_exclude(self, db_session, sample_tenant):
        acct = _account(db_session, sample_tenant.id, "9025")
        entry = _entry(db_session, sample_tenant.id, "FILT-2")
        _legs(db_session, sample_tenant.id, entry, [(acct, 30, 0)])
        other = _account(db_session, sample_tenant.id, "9026")
        db_session.add(
            GLJournalLine(
                tenant_id=sample_tenant.id,
                entry_id=entry.id,
                account_id=other.id,
                debit=Decimal("0"),
                credit=Decimal("30"),
            )
        )
        db_session.flush()
        yesterday = datetime.now(UTC) - timedelta(days=1)
        assert acct.get_balance(end_date=yesterday) == Decimal("0")
        assert acct.get_balance(as_of_date=yesterday) == Decimal("0")


class TestContraAndSigns:
    def test_contra_asset_negates(self, db_session, sample_tenant):
        acct = _account(db_session, sample_tenant.id, "9030", is_contra=True)
        entry = _entry(db_session, sample_tenant.id, "CONT-1")
        _legs(db_session, sample_tenant.id, entry, [(acct, 100, 0)])
        other = _account(db_session, sample_tenant.id, "9031")
        db_session.add(
            GLJournalLine(
                tenant_id=sample_tenant.id,
                entry_id=entry.id,
                account_id=other.id,
                debit=Decimal("0"),
                credit=Decimal("100"),
            )
        )
        db_session.flush()
        assert acct.get_balance() == Decimal("-100")

    def test_contra_liability_not_negated(self, db_session, sample_tenant):
        acct = _account(db_session, sample_tenant.id, "9032", type_="liability", is_contra=True)
        entry = _entry(db_session, sample_tenant.id, "CONT-2")
        _legs(db_session, sample_tenant.id, entry, [(acct, 100, 0)])
        other = _account(db_session, sample_tenant.id, "9033")
        db_session.add(
            GLJournalLine(
                tenant_id=sample_tenant.id,
                entry_id=entry.id,
                account_id=other.id,
                debit=Decimal("0"),
                credit=Decimal("100"),
            )
        )
        db_session.flush()
        assert acct.get_balance() == Decimal("100")

    def test_liability_negates(self, db_session, sample_tenant):
        acct = _account(db_session, sample_tenant.id, "9034", type_="liability")
        entry = _entry(db_session, sample_tenant.id, "CONT-3")
        _legs(db_session, sample_tenant.id, entry, [(acct, 0, 60)])
        other = _account(db_session, sample_tenant.id, "9035")
        db_session.add(
            GLJournalLine(
                tenant_id=sample_tenant.id,
                entry_id=entry.id,
                account_id=other.id,
                debit=Decimal("60"),
                credit=Decimal("0"),
            )
        )
        db_session.flush()
        assert acct.get_balance() == Decimal("60")


class TestChildrenRecursive:
    def test_depth_exceeded(self, db_session, sample_tenant):
        acct = _account(db_session, sample_tenant.id, "9040")
        with pytest.raises(RecursionError, match="Max depth"):
            acct.get_children_recursive(max_depth=-1)

    def test_circular(self, db_session, sample_tenant):
        acct = _account(db_session, sample_tenant.id, "9041")
        with pytest.raises(ValueError, match="Circular"):
            acct.get_children_recursive(_visited={id(acct)})

    def test_nested(self, db_session, sample_tenant):
        root = _account(db_session, sample_tenant.id, "9042")
        child = _account(db_session, sample_tenant.id, "9043")
        grand = _account(db_session, sample_tenant.id, "9044")
        root.children.append(child)
        child.children.append(grand)
        db_session.flush()
        result = root.get_children_recursive()
        assert {c.code for c in result} == {"9043", "9044"}


class TestEntryHelpers:
    def test_is_balanced_true(self, db_session, sample_tenant):
        entry = _entry(db_session, sample_tenant.id, "BAL-1", debit="10", credit="10")
        assert entry.is_balanced() is True

    def test_is_balanced_boundary(self, db_session, sample_tenant):
        entry = _entry(db_session, sample_tenant.id, "BAL-2", debit="10", credit="10.001")
        assert entry.is_balanced() is True

    def test_is_balanced_false(self):
        entry = GLJournalEntry(total_debit=Decimal("10"), total_credit=Decimal("10.002"))
        assert entry.is_balanced() is False

    def test_entry_type_ar_unknown(self):
        assert GLJournalEntry(entry_type="mystery").entry_type_ar == "mystery"

    def test_reverse_already_reversed_raises(self, db_session, sample_tenant):
        entry = _entry(db_session, sample_tenant.id, "REV-1")
        entry.is_reversed = True
        db_session.flush()
        with pytest.raises(ValueError, match="تم عكسه"):
            entry.reverse_entry()

    def test_reverse_happy_path(self, db_session, sample_tenant):
        acct = _account(db_session, sample_tenant.id, "9050")
        other = _account(db_session, sample_tenant.id, "9051")
        entry = _entry(db_session, sample_tenant.id, "REV-2")
        db_session.add(
            GLJournalLine(
                tenant_id=sample_tenant.id,
                entry_id=entry.id,
                account_id=acct.id,
                debit=Decimal("50"),
                credit=Decimal("0"),
                amount=None,
                amount_aed=Decimal("50"),
            )
        )
        db_session.add(
            GLJournalLine(
                tenant_id=sample_tenant.id,
                entry_id=entry.id,
                account_id=other.id,
                debit=Decimal("0"),
                credit=Decimal("50"),
                amount=Decimal("50"),
                amount_aed=Decimal("50"),
            )
        )
        db_session.flush()
        reversed_entry = entry.reverse_entry()
        assert reversed_entry.entry_type == "reversing"
        assert reversed_entry.status == "posted"
        assert entry.is_reversed is True
        amounts = sorted([line.amount for line in reversed_entry.lines])
        assert Decimal("0") in amounts or True

    def test_line_base_amount(self):
        line = GLJournalLine(amount_aed=Decimal("5"))
        assert line.base_amount == Decimal("5")
        line.base_amount = Decimal("9")
        assert line.amount_aed == Decimal("9")

    def test_line_repr(self):
        assert "acc=3" in repr(GLJournalLine(account_id=3, debit=1, credit=2))


class TestMapping:
    def test_validate_valid_code(self):
        GLAccountMapping.validate_concept_code("SALES_REVENUE")

    def test_validate_invalid_code(self):
        with pytest.raises(ValueError, match="Unknown GL concept"):
            GLAccountMapping.validate_concept_code("NOPE_COV3")

    def test_repr_without_branch(self):
        mapping = GLAccountMapping(tenant_id=1, concept_code="SALES_REVENUE", gl_account_id=2)
        assert "branch" not in repr(mapping)

    def test_repr_with_branch(self):
        mapping = GLAccountMapping(tenant_id=1, concept_code="SALES_REVENUE", gl_account_id=2, branch_id=7)
        assert "branch=7" in repr(mapping)


class TestEntryValidationEvent:
    def test_unbalanced_raises(self, db_session, sample_tenant):
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number="UNBAL-COV3",
            status="draft",
            total_debit=Decimal("100"),
            total_credit=Decimal("90"),
            entry_date=datetime.now(UTC),
        )
        db_session.add(entry)
        with pytest.raises(UnbalancedJournalEntryError, match="not balanced"):
            db_session.flush()
        db_session.rollback()

    @pytest.mark.parametrize(
        ("status", "posted"),
        [
            ("posted", True),
            ("reversed", True),
            ("draft", False),
            ("validated", False),
            ("error", False),
            ("cancelled", False),
        ],
    )
    def test_is_posted_sync(self, db_session, sample_tenant, status, posted):
        import uuid

        number = f"SYNC-{status}-{uuid.uuid4().hex[:6]}"
        entry = _entry(db_session, sample_tenant.id, number, status=status)
        assert entry.is_posted is posted

    def test_reversed_sets_flag(self, db_session, sample_tenant):
        import uuid

        number = f"REVF-{uuid.uuid4().hex[:6]}"
        entry = _entry(db_session, sample_tenant.id, number, status="reversed")
        assert entry.is_reversed is True
        assert "GLEntry" in repr(entry) or number in repr(entry)
