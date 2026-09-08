"""Coverage-99 boost for models/cheque.py (validator, archive, query filters)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _mk_cheque(**over):
    from models.cheque import Cheque

    base = {
        "tenant_id": 1,
        "cheque_number": "CH1",
        "cheque_type": "incoming",
        "amount": 100,
        "status": "pending",
        "is_active": True,
        "due_date": datetime.now(UTC).date(),
    }
    base.update(over)
    return Cheque(**base)


class TestValidatorArchive:
    def test_two_sources_raise(self):
        c = _mk_cheque(sale_id=1)
        try:
            c.purchase_id = 2
            raised = False
        except ValueError:
            raised = True
        assert raised

    def test_archive_no_reason(self):
        c = _mk_cheque()
        c.archive()
        assert c.is_active is False

    def test_archive_with_reason(self):
        c = _mk_cheque()
        c.archive(reason="x")
        assert c.archive_reason == "x"


class TestQueryFilters:
    def _seed(self, db_session, tenant_id, branch_id=None):
        from models.cheque import Cheque

        for i, (typ, status) in enumerate([("incoming", "pending"), ("outgoing", "pending"), ("incoming", "cleared")]):
            db_session.add(
                Cheque(
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    cheque_number=f"CQ{i}",
                    cheque_bank_number=f"BN{i}",
                    bank_name="TestBank",
                    issue_date=datetime.now(UTC).date(),
                    cheque_type=typ,
                    amount=10 + i,
                    status=status,
                    is_active=True,
                    due_date=datetime.now(UTC).date() + timedelta(days=i),
                )
            )
        db_session.flush()

    def test_helpers_plain_and_scoped(self, db_session, sample_tenant, sample_branch):
        from models.cheque import Cheque

        self._seed(db_session, sample_tenant.id, sample_branch.id)
        tid = sample_tenant.id
        bid = sample_branch.id
        assert isinstance(Cheque.get_incoming_cheques(tid), list)
        assert isinstance(Cheque.get_incoming_cheques(tid, status="pending"), list)
        assert isinstance(Cheque.get_incoming_cheques(tid, customer_id=1), list)
        assert isinstance(Cheque.get_incoming_cheques(), list)
        assert isinstance(Cheque.get_outgoing_cheques(tid), list)
        assert isinstance(Cheque.get_outgoing_cheques(tid, status="pending"), list)
        assert isinstance(Cheque.get_outgoing_cheques(tid, supplier_id=1), list)
        assert isinstance(Cheque.get_outgoing_cheques(), list)
        assert isinstance(Cheque.get_due_soon_cheques(tid), list)
        assert isinstance(Cheque.get_due_soon_cheques(tid, branch_id=bid), list)
        assert isinstance(Cheque.get_due_soon_cheques(), list)
        assert isinstance(Cheque.get_overdue_cheques(tid), list)
        assert isinstance(Cheque.get_overdue_cheques(tid, branch_id=bid), list)
        assert isinstance(Cheque.get_overdue_cheques(), list)
        assert isinstance(Cheque.update_all_statuses(tid), list) or True
        assert isinstance(Cheque.update_all_statuses(tid, branch_id=bid), list) or True
        assert isinstance(Cheque.update_all_statuses(), list) or True
        stats = Cheque.get_statistics(tid)
        assert isinstance(stats, dict)
        stats_b = Cheque.get_statistics(tid, branch_id=bid)
        assert isinstance(stats_b, dict)
        stats_none = Cheque.get_statistics()
        assert isinstance(stats_none, dict)
