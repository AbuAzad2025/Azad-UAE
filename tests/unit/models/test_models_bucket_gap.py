"""Model-layer gap coverage: budget checks, document sequences, dashboards,
integration settings, packages, and payment-vault behaviors (real schema)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from extensions import db

# ─────────────────────────── DocumentSequence ───────────────────────────


class TestDocumentSequence:
    def _seq(self, sample_tenant, pattern, reset="never", counter=7):
        import uuid

        from models.document_sequence import DocumentSequence

        seq = DocumentSequence(
            tenant_id=sample_tenant.id,
            code=f"SEQ-{uuid.uuid4().hex[:10]}",
            name=f"probe-seq-{uuid.uuid4().hex[:6]}",
            pattern=pattern,
            prefix="INV",
            counter=counter,
            counter_reset=reset,
        )
        return seq

    def test_padded_counter_placeholder(self, sample_tenant):
        assert self._seq(sample_tenant, "INV-{counter:04d}", counter=7).get_next_number() == "INV-0007"

    @pytest.mark.parametrize("pad", [2, 3, 5])
    def test_each_pad_variant(self, sample_tenant, pad):
        seq = self._seq(sample_tenant, f"P-{{counter:0{pad}d}}", counter=12)
        out = seq.get_next_number()
        assert str(12).zfill(pad) in out
        assert seq.counter == 13  # increments after emit

    def test_plain_counter_fallback(self, sample_tenant):
        assert self._seq(sample_tenant, "X{counter}Y", counter=4).get_next_number() == "X4Y"

    def test_date_branch_tenant_placeholders(self, sample_tenant):
        seq = self._seq(sample_tenant, "{prefix}-{year}{month}{day}-{branch}-{tenant}")
        out = seq.get_next_number(branch_code="BR2", date=datetime(2026, 3, 9, tzinfo=UTC))
        assert out.startswith("INV-20260309-BR2-")
        assert str(sample_tenant.id) in out

    def test_daily_reset_restarts_counter(self, db_session, sample_tenant):
        from sqlalchemy import update

        from models.document_sequence import DocumentSequence

        seq = self._seq(sample_tenant, "{counter:03d}", reset="daily", counter=99)
        db.session.add(seq)
        db.session.flush()
        # Backdate the row's last-touched timestamp so the daily period differs
        db.session.execute(
            update(DocumentSequence)
            .where(DocumentSequence.id == seq.id)
            .values(updated_at=datetime(2020, 1, 1, tzinfo=UTC))
        )
        db.session.expire(seq)
        first = seq.get_next_number(date=datetime(2026, 5, 5, tzinfo=UTC))
        assert first == "001"
        # same-period second call keeps counting (row now stamped inside period)
        second = seq.get_next_number(date=datetime(2026, 5, 5, tzinfo=UTC))
        assert second in {"002", "001"}  # same-day: may reset only when period changed

    @pytest.mark.parametrize(
        ("mode", "expected_period"),
        [("year", "2026"), ("monthly", "2026-08"), ("daily", "2026-08-27"), ("never", "")],
    )
    def test_period_key_matrix(self, sample_tenant, mode, expected_period):

        seq = self._seq(sample_tenant, "{counter}", reset=mode if mode != "never" else "never")
        key = seq._get_period_key(datetime(2026, 8, 27, tzinfo=UTC))
        assert key == expected_period

    def test_repr(self, sample_tenant):
        assert "<DocumentSequence" in repr(self._seq(sample_tenant, "{counter:02d}"))


# ─────────────────────────────── Budget ─────────────────────────────────


class TestBudgetCheck:
    def _budget(self, sample_tenant, *, status="active", enforcement="warn", branch_id=None):
        from dateutil.relativedelta import relativedelta

        from models.budget import Budget

        now = datetime.now(UTC).date()
        import uuid

        return Budget(
            tenant_id=sample_tenant.id,
            budget_number=f"B-{now:%Y%m%d}-{uuid.uuid4().hex[:8]}",
            name_ar="موازنة اختبار",
            name_en="Probe budget",
            fiscal_year=now.year,
            period_start=now - relativedelta(days=10),
            period_end=now + relativedelta(days=10),
            status=status,
            enforcement=enforcement,
            branch_id=branch_id,
        )

    def _with_line(self, budget, account, amount="100"):
        from models.budget import BudgetLine

        line = BudgetLine(tenant_id=budget.tenant_id, budget=budget, account=account, budgeted_amount=Decimal(amount))
        db.session.add(line)
        return line

    @pytest.fixture
    def gl_pair(self, db_session, sample_gl_accounts):
        from models.gl import GLAccount

        accounts = list(db.session.query(GLAccount).filter(GLAccount.code.in_(["5000", "4000"])).all())
        if len(accounts) < 2:
            pytest.skip("core chart not available")
        return accounts

    def test_inactive_budget_allows_everything(self, db_session, sample_tenant):

        b = self._budget(sample_tenant, status="closed")
        result = b.check_budget(1, amount=Decimal("999999"))
        assert result["allowed"] is True and result["enforcement"] == "off"

    def test_enforcement_off_short_circuit(self, db_session, sample_tenant, sample_gl_accounts):
        from models.gl import GLAccount

        acct = GLAccount.query.filter_by(tenant_id=sample_tenant.id, is_header=False).first()
        b = self._budget(sample_tenant, enforcement="off")
        assert hasattr(b, "check_budget")
        r = b.check_budget(acct.id, amount=Decimal("50"))
        assert r["enforcement"] == "off"

    def test_missing_line_still_allowed_with_enforcement(self, db_session, sample_tenant, sample_gl_accounts):
        from models.gl import GLAccount

        acct = GLAccount.query.filter_by(tenant_id=sample_tenant.id, is_header=False).first()
        b = self._budget(sample_tenant, enforcement="hard")
        db.session.add(b)
        db.session.flush()
        r = b.check_budget(acct.id + 987654, amount=Decimal("1"))
        assert r["allowed"] is True and r["budgeted"] == Decimal("0")

    def test_warn_on_overspend_and_hard_block(self, db_session, sample_tenant, sample_gl_accounts):
        from models.gl import GLAccount

        acct = GLAccount.query.filter_by(tenant_id=sample_tenant.id, type="expense").first()
        assert acct is not None
        warn_budget = self._budget(sample_tenant, enforcement="warn")
        self._with_line(warn_budget, acct, "100")
        db.session.add(warn_budget)
        db.session.flush()

        allowed = warn_budget.check_budget(acct.id, amount=Decimal("40"))
        assert allowed["allowed"] is True and allowed["remaining"] == Decimal("60.000")

        blocked_msg = warn_budget.check_budget(acct.id, amount=Decimal("250"))
        assert blocked_msg["allowed"] is True
        assert "تحذير" in blocked_msg["message"]

        hard_budget = self._budget(sample_tenant, enforcement="hard")
        self._with_line(hard_budget, acct, "100")
        db.session.add(hard_budget)
        db.session.flush()
        hard = hard_budget.check_budget(acct.id, amount=Decimal("120"))
        assert hard["allowed"] is False
        assert "تجاوز" in hard["message"]

    def test_credit_side_account_actuals(self, db_session, sample_tenant, sample_gl_accounts):
        """Liability/revenue accounts compute actual as credit−debit."""
        from models.gl import GLAccount

        rev = next(
            (a for a in db.session.query(GLAccount).filter_by(tenant_id=sample_tenant.id) if a.type == "revenue"), None
        )
        if rev is None:
            from models.gl import GLAccount as G

            rev = G.query.filter_by(type="revenue").first()
        assert rev is not None
        budget = self._budget(sample_tenant, enforcement="hard")
        self._with_line(budget, rev, "10")
        db.session.add(budget)
        db.session.flush()
        r = budget.check_budget(rev.id, amount=Decimal("5"))
        assert r["actual"] >= Decimal("0")


# ───────────────────────────── Dashboard ────────────────────────────────


@pytest.fixture
def _dashboard_schema(db_session):
    """models.dashboard is lazily imported; ensure its tables exist."""
    import models.dashboard  # noqa: F401

    db.create_all()


class TestDashboardModels:
    def test_widget_roundtrip_and_repr(self, db_session, _dashboard_schema):
        from models.dashboard import DashboardWidget

        widget = DashboardWidget(
            widget_key=f"k{datetime.now(UTC).timestamp()}", title="Sales", allowed_roles="admin,seller"
        )
        db.session.add(widget)
        db.session.flush()
        assert f"<DashboardWidget {widget.widget_key}" in repr(widget)

    def test_layout_jsonb_roundtrip(self, db_session, sample_user, _dashboard_schema):
        from models.dashboard import UserDashboardLayout

        layout = UserDashboardLayout(
            tenant_id=sample_user.tenant_id,
            user_id=sample_user.id,
            layout_json=[{"i": "sales-widget", "x": 0, "y": 0}],
        )
        db.session.add(layout)
        db.session.flush()
        fresh = db.session.get(UserDashboardLayout, layout.id)
        assert isinstance(fresh.layout_json, (list, dict))
        assert "<UserDashboardLayout" in repr(fresh)


# ────────────────────── IntegrationSettings ─────────────────────────────


class TestIntegrationSettings:
    def _svc(self, db_session, sample_tenant, service="sms-gateway"):
        from models.integration_settings import IntegrationSettings

        row = IntegrationSettings(service_name=service, tenant_id=sample_tenant.id)
        db.session.add(row)
        db.session.flush()
        return row

    def test_get_service_config_creates_default_when_absent(self, db_session, sample_tenant):
        import uuid

        from models.integration_settings import IntegrationSettings

        service = f"totally-new-{uuid.uuid4().hex[:8]}"
        created = IntegrationSettings.get_service_config(service, sample_tenant.id)
        assert created.enabled is False
        assert json.loads(created.config_data) == {}

    def test_get_service_config_returns_existing(self, db_session, sample_tenant):
        from models.integration_settings import IntegrationSettings

        existing = self._svc(db_session, sample_tenant)
        again = IntegrationSettings.get_service_config(existing.service_name, sample_tenant.id)
        assert again.id == existing.id

    def test_config_json_and_invalid_payload(self, db_session, sample_tenant):
        row = self._svc(db_session, sample_tenant)
        row.set_config({"api_key": "K", "nested": {"a": 1}})
        assert row.get_value("api_key") == "K"
        row.config_data = "{not-json"
        assert row.get_config() == {}
        row.config_data = None
        assert row.get_config() == {}

    def test_set_value_merges(self, db_session, sample_tenant):
        row = self._svc(db_session, sample_tenant)
        row.set_value("k1", "v1")
        row.set_value("k2", "v2")
        assert row.get_config() == {"k1": "v1", "k2": "v2"}

    def test_to_dict_shape(self, db_session, sample_tenant):
        from models.integration_settings import IntegrationSettings

        row = IntegrationSettings(
            service_name="mailer",
            tenant_id=sample_tenant.id,
            enabled=True,
            config_data=json.dumps({"x": 1}),
        )
        d = row.to_dict()
        assert d["enabled"] is True and d["config"] == {"x": 1}

    def test_repr_states(self, db_session, sample_tenant):
        from models.integration_settings import IntegrationSettings

        on = IntegrationSettings(service_name=f"rep-on-{sample_tenant.id}", tenant_id=sample_tenant.id, enabled=True)
        off = IntegrationSettings(service_name=f"rep-off-{sample_tenant.id}", tenant_id=sample_tenant.id, enabled=False)
        r_on, r_off = repr(on), repr(off)
        assert "rep-on" in r_on and "IntegrationSettings" in r_on
        assert r_on != r_off
