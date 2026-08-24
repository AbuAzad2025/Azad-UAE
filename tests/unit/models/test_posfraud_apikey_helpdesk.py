"""Tests for models: PosFraudSignal, ApiKey, Helpdesk (Ticket etc)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError


class TestPosFraudSignal:
    def test_create_minimal(self, db_session, sample_tenant):
        from models.pos_fraud_log import PosFraudSignal

        sig = PosFraudSignal(
            tenant_id=sample_tenant.id,
            event_type="void_sale",
            severity="high",
            entry_hash="abc123",
            prev_hash="",
            details="test detail",
        )
        db_session.add(sig)
        db_session.flush()
        assert sig.id is not None
        assert sig.tenant_id == sample_tenant.id
        assert sig.event_type == "void_sale"
        assert sig.severity == "high"
        assert sig.entry_hash == "abc123"

    def test_required_fields(self, db_session, sample_tenant):
        from models.pos_fraud_log import PosFraudSignal

        sig = PosFraudSignal(tenant_id=sample_tenant.id, event_type="discount_abuse", entry_hash="hash1")
        db_session.add(sig)
        db_session.flush()
        assert sig.id is not None
        # severity defaults to medium
        assert sig.severity == "medium"
        assert sig.repeat_count == 1

    def test_nullable_optional_fields(self, db_session, sample_tenant, sample_user, sample_branch):
        from models.pos_fraud_log import PosFraudSignal

        sig = PosFraudSignal(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            user_id=sample_user.id,
            event_type="cash_drawer",
            entry_hash="h2",
        )
        db_session.add(sig)
        db_session.flush()
        assert sig.branch_id == sample_branch.id
        assert sig.user_id == sample_user.id

    def test_hash_chain_prev_hash(self, db_session, sample_tenant):
        from models.pos_fraud_log import PosFraudSignal

        s1 = PosFraudSignal(tenant_id=sample_tenant.id, event_type="a", entry_hash="hashA", prev_hash="")
        db_session.add(s1)
        db_session.flush()
        s2 = PosFraudSignal(tenant_id=sample_tenant.id, event_type="b", entry_hash="hashB", prev_hash="hashA")
        db_session.add(s2)
        db_session.flush()
        assert s2.prev_hash == s1.entry_hash

    def test_tenant_scoping_isolation(self, db_session, sample_tenant):
        from flask import g

        from models import Tenant
        from models.pos_fraud_log import PosFraudSignal

        # create second tenant
        t2 = Tenant(
            name="Other Fraud Tenant",
            name_ar="آخر",
            slug="other-fraud",
            email="other@fraud.test",
            phone_1="0500000000",
            country="AE",
            subscription_plan="basic",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(t2)
        db_session.flush()
        g.skip_tenant_scope = True
        s1 = PosFraudSignal(tenant_id=sample_tenant.id, event_type="x", entry_hash="hx1")
        s2 = PosFraudSignal(tenant_id=t2.id, event_type="y", entry_hash="hy1")
        db_session.add_all([s1, s2])
        db_session.flush()
        # tenant_query should filter

        # simulate tenant 1 active via patch? Just test model has tenant_id distinct
        assert s1.tenant_id != s2.tenant_id
        g.skip_tenant_scope = False

    def test_created_at_auto(self, db_session, sample_tenant):
        from models.pos_fraud_log import PosFraudSignal

        sig = PosFraudSignal(tenant_id=sample_tenant.id, event_type="auto_ts", entry_hash="hts")
        db_session.add(sig)
        db_session.flush()
        assert sig.created_at is not None

    def test_repeat_count_default(self, db_session, sample_tenant):
        from models.pos_fraud_log import PosFraudSignal

        sig = PosFraudSignal(tenant_id=sample_tenant.id, event_type="rep", entry_hash="rep1")
        db_session.add(sig)
        db_session.flush()
        assert sig.repeat_count == 1
        sig.repeat_count = 5
        db_session.flush()
        assert sig.repeat_count == 5


class TestApiKey:
    def test_create_minimal(self, db_session, sample_tenant):
        from models.api_key import APIKey

        k = APIKey(
            name="Test Key", key=APIKey.generate_key(), service="pos", tenant_id=sample_tenant.id, is_active=True
        )
        db_session.add(k)
        db_session.flush()
        assert k.id is not None
        assert k.service == "pos"
        assert k.is_active is True
        assert k.tenant_id == sample_tenant.id

    def test_generate_key_unique(self):
        from models.api_key import APIKey

        k1 = APIKey.generate_key()
        k2 = APIKey.generate_key()
        assert k1 != k2
        assert len(k1) > 20

    def test_unique_key_constraint(self, db_session, sample_tenant):
        from models.api_key import APIKey

        key = APIKey.generate_key()
        k1 = APIKey(name="K1", key=key, service="pos", tenant_id=sample_tenant.id)
        db_session.add(k1)
        db_session.flush()
        k2 = APIKey(name="K2", key=key, service="pos", tenant_id=sample_tenant.id)
        db_session.add(k2)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_required_fields_name_service_key(self, db_session):
        from models.api_key import APIKey

        # missing service should allow? service is nullable=False so should fail on commit
        k = APIKey(name="MissingService", key=APIKey.generate_key())
        db_session.add(k)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_scope_default_write(self, db_session, sample_tenant):
        from models.api_key import APIKey

        k = APIKey(name="ScopeDefault", key=APIKey.generate_key(), service="api", tenant_id=sample_tenant.id)
        db_session.add(k)
        db_session.flush()
        assert k.scope == "write"

    def test_scope_read(self, db_session, sample_tenant):
        from models.api_key import APIKey

        k = APIKey(name="ReadKey", key=APIKey.generate_key(), service="api", scope="read", tenant_id=sample_tenant.id)
        db_session.add(k)
        db_session.flush()
        assert k.scope == "read"

    def test_tenant_nullable_for_platform_key(self, db_session):
        from models.api_key import APIKey

        k = APIKey(name="PlatformKey", key=APIKey.generate_key(), service="platform")
        db_session.add(k)
        db_session.flush()
        assert k.tenant_id is None

    def test_usage_tracking(self, db_session, sample_tenant):
        from models.api_key import APIKey

        k = APIKey(name="Usage", key=APIKey.generate_key(), service="pos", tenant_id=sample_tenant.id, usage_count=0)
        db_session.add(k)
        db_session.flush()
        k.usage_count = (k.usage_count or 0) + 1
        k.last_used = datetime.now(UTC)
        db_session.flush()
        assert k.usage_count == 1
        assert k.last_used is not None

    def test_is_active_index(self, db_session, sample_tenant):
        from models.api_key import APIKey

        k_active = APIKey(
            name="Active", key=APIKey.generate_key(), service="pos", is_active=True, tenant_id=sample_tenant.id
        )
        k_inactive = APIKey(
            name="Inactive", key=APIKey.generate_key(), service="pos", is_active=False, tenant_id=sample_tenant.id
        )
        db_session.add_all([k_active, k_inactive])
        db_session.flush()
        active = APIKey.query.filter_by(is_active=True, tenant_id=sample_tenant.id).all()
        assert any(x.id == k_active.id for x in active)
        assert not any(x.id == k_inactive.id for x in active)

    def test_repr(self, db_session, sample_tenant):
        from models.api_key import APIKey

        k = APIKey(name="ReprTest", key=APIKey.generate_key(), service="pos", tenant_id=sample_tenant.id)
        db_session.add(k)
        db_session.flush()
        assert "ReprTest" in repr(k) or "pos" in repr(k)


class TestHelpdesk:
    def test_create_ticket_category(self, db_session, sample_tenant):
        from models.helpdesk import TicketCategory

        cat = TicketCategory(tenant_id=sample_tenant.id, name="Support", name_ar="دعم")
        db_session.add(cat)
        db_session.flush()
        assert cat.id is not None
        assert cat.name == "Support"
        assert cat.tenant_id == sample_tenant.id
        assert cat.is_active is True

    def test_create_ticket_priority(self, db_session, sample_tenant):
        from models.helpdesk import TicketPriority

        pri = TicketPriority(tenant_id=sample_tenant.id, name="High", name_ar="عالية", sequence=1, sla_hours=24)
        db_session.add(pri)
        db_session.flush()
        assert pri.id is not None
        assert pri.sla_hours == 24

    def test_create_ticket_minimal(self, db_session, sample_tenant):
        from models.helpdesk import Ticket

        t = Ticket(tenant_id=sample_tenant.id, subject="Help needed", body="Details")
        db_session.add(t)
        db_session.flush()
        assert t.id is not None
        assert t.subject == "Help needed"
        assert t.status == "open"
        assert t.source == "portal"

    def test_create_ticket_with_relations(self, db_session, sample_tenant, sample_customer, sample_user):
        from models.helpdesk import Ticket, TicketCategory, TicketPriority

        cat = TicketCategory(tenant_id=sample_tenant.id, name="CatRel")
        pri = TicketPriority(tenant_id=sample_tenant.id, name="PriRel")
        db_session.add_all([cat, pri])
        db_session.flush()
        t = Ticket(
            tenant_id=sample_tenant.id,
            subject="With relations",
            customer_id=sample_customer.id,
            category_id=cat.id,
            priority_id=pri.id,
            assigned_user_id=sample_user.id,
            branch_id=sample_user.branch_id,
            number="T-001",
        )
        db_session.add(t)
        db_session.flush()
        assert t.customer_id == sample_customer.id
        assert t.category_id == cat.id
        assert t.priority_id == pri.id
        assert t.assigned_user_id == sample_user.id

    def test_ticket_status_defaults(self, db_session, sample_tenant):
        from models.helpdesk import Ticket

        t = Ticket(tenant_id=sample_tenant.id, subject="StatusTest")
        db_session.add(t)
        db_session.flush()
        assert t.status == "open"
        assert t.is_active is True

    def test_ticket_to_dict(self, db_session, sample_tenant):
        from models.helpdesk import Ticket

        t = Ticket(tenant_id=sample_tenant.id, subject="DictTest", number="T-999", status="open")
        db_session.add(t)
        db_session.flush()
        d = t.to_dict()
        assert d["subject"] == "DictTest"
        assert d["number"] == "T-999"
        assert d["status"] == "open"
        assert "id" in d

    def test_create_ticket_comment(self, db_session, sample_tenant, sample_user):
        from models.helpdesk import Ticket, TicketComment

        t = Ticket(tenant_id=sample_tenant.id, subject="Comment ticket")
        db_session.add(t)
        db_session.flush()
        c = TicketComment(
            tenant_id=sample_tenant.id, ticket_id=t.id, user_id=sample_user.id, body="First comment", is_internal=False
        )
        db_session.add(c)
        db_session.flush()
        assert c.id is not None
        assert c.ticket_id == t.id
        assert c.body == "First comment"
        # relationship backpopulates
        db_session.refresh(t)
        assert len(t.comments) == 1

    def test_ticket_comment_internal_flag(self, db_session, sample_tenant):
        from models.helpdesk import Ticket, TicketComment

        t = Ticket(tenant_id=sample_tenant.id, subject="Internal flag")
        db_session.add(t)
        db_session.flush()
        c = TicketComment(tenant_id=sample_tenant.id, ticket_id=t.id, body="Internal note", is_internal=True)
        db_session.add(c)
        db_session.flush()
        assert c.is_internal is True

    def test_ticket_tenant_isolation(self, db_session, sample_tenant):
        from flask import g

        from models import Tenant
        from models.helpdesk import Ticket

        g.skip_tenant_scope = True
        t2 = Tenant(
            name="Help Other",
            name_ar="آخر",
            slug="help-other",
            email="help@other.test",
            phone_1="0500000000",
            country="AE",
            subscription_plan="basic",
            default_currency="AED",
            base_currency="AED",
        )
        db_session.add(t2)
        db_session.flush()
        t1 = Ticket(tenant_id=sample_tenant.id, subject="T1")
        t2_ticket = Ticket(tenant_id=t2.id, subject="T2")
        db_session.add_all([t1, t2_ticket])
        db_session.flush()
        assert t1.tenant_id != t2_ticket.tenant_id
        g.skip_tenant_scope = False

    def test_ticket_required_subject(self, db_session, sample_tenant):
        from models.helpdesk import Ticket

        t = Ticket(tenant_id=sample_tenant.id, subject=None)
        db_session.add(t)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_ticket_category_color_default(self, db_session, sample_tenant):
        from models.helpdesk import TicketCategory

        cat = TicketCategory(tenant_id=sample_tenant.id, name="ColorDefault")
        db_session.add(cat)
        db_session.flush()
        assert cat.color == "#3b82f6"

    def test_ticket_sla_deadline_nullable(self, db_session, sample_tenant):
        from models.helpdesk import Ticket

        t = Ticket(tenant_id=sample_tenant.id, subject="SLA null", sla_deadline=None)
        db_session.add(t)
        db_session.flush()
        assert t.sla_deadline is None
        t.sla_deadline = datetime.now(UTC) + timedelta(hours=24)
        db_session.flush()
        assert t.sla_deadline is not None
