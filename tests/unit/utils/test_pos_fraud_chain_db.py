"""Insert-only POS fraud signal chain (utils/pos_security.py) against real DB."""

from __future__ import annotations

import pytest

from extensions import db
from models import PosFraudSignal
from utils.pos_security import log_pos_fraud_signal, verify_pos_fraud_chain


@pytest.fixture
def tenant_id_fixture(sample_tenant):
    return sample_tenant.id


class TestLogPosFraudSignal:
    def test_no_tenant_returns_none(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=None)
        assert log_pos_fraud_signal("void_line") is None

    def test_non_numeric_tenant_returns_none(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value="not-a-number")
        assert log_pos_fraud_signal("void_line") is None

    def test_first_signal_medium_with_empty_prev_hash(self, db_session, sample_user, tenant_id_fixture):
        row = log_pos_fraud_signal(
            "void_line",
            user_id=sample_user.id,
            session_id=None,
            details={"reason": "probe"},
            tenant_id=tenant_id_fixture,
        )
        assert row is not None
        assert row.repeat_count == 1
        assert row.severity == "medium"
        assert row.prev_hash == ""
        assert len(row.entry_hash) == 64
        assert '"reason"' in row.details

    def test_repeat_within_window_escalates_to_high(self, db_session, sample_user, tenant_id_fixture):
        for _ in range(3):
            row = log_pos_fraud_signal("no_sale_drawer", user_id=sample_user.id, tenant_id=tenant_id_fixture)
        assert row.repeat_count == 3
        assert row.severity == "high"

    def test_anonymous_signal_has_blank_user(self, db_session, tenant_id_fixture):
        row = log_pos_fraud_signal("pay_in", tenant_id=tenant_id_fixture)
        assert row.user_id is None

    def test_chain_valid_then_tamper_detected(self, db_session, sample_user, tenant_id_fixture):
        log_pos_fraud_signal("pay_out", user_id=sample_user.id, tenant_id=tenant_id_fixture)
        log_pos_fraud_signal("pay_out", user_id=None, tenant_id=tenant_id_fixture)
        assert verify_pos_fraud_chain(tenant_id_fixture) is True

        rows = (
            PosFraudSignal.query.filter(PosFraudSignal.tenant_id == int(tenant_id_fixture))
            .order_by(PosFraudSignal.id.asc())
            .all()
        )
        rows[0].entry_hash = "0" * 64
        db.session.flush()
        assert verify_pos_fraud_chain(tenant_id_fixture) is False

    def test_prev_hash_gap_breaks_chain(self, db_session, sample_user, tenant_id_fixture):
        first = log_pos_fraud_signal("pay_in", user_id=sample_user.id, tenant_id=tenant_id_fixture)
        second = log_pos_fraud_signal("pay_in", user_id=sample_user.id, tenant_id=tenant_id_fixture)
        second.prev_hash = "f" * 64
        db.session.flush()
        # chain now invalid (stored linkage broken at row2)
        assert first.entry_hash != second.prev_hash
        assert verify_pos_fraud_chain(tenant_id_fixture) is False
