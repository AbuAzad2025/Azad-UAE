"""Unit tests for services/owner_ops_service.py — OwnerOpsService query methods.

Covers the methods backing routes/owner/{monitoring,core,database,settings}.py
and routes/owner_admin.py: scoping, ordering, and boundary behavior against the
real test database. Rows are created via db_session + flush and rolled back by
the autouse transaction fixture.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from werkzeug.exceptions import NotFound

from services.owner_ops_service import OwnerOpsService


def _uid() -> str:
    return uuid.uuid4().hex[:8]


# ── login history ────────────────────────────────────────────────────────────


class TestLoginHistory:
    def test_pagination_scopes_by_tenant_and_filters(self, db_session, sample_tenant, sample_user):
        from models.login_history import LoginHistory

        mine = LoginHistory(user_id=sample_user.id, username=sample_user.username, success=True)
        other = LoginHistory(username="ghost-" + _uid(), success=False)
        db_session.add_all([mine, other])
        db_session.flush()

        page = OwnerOpsService.login_history_pagination(1, sample_tenant.id, None, None)
        assert mine in page.items
        assert all(item.user is not None for item in page.items)

        filtered = OwnerOpsService.login_history_pagination(1, sample_tenant.id, sample_user.id, "true")
        assert mine in filtered.items
        assert all(item.success for item in filtered.items)

    def test_pagination_success_false_filter(self, db_session, sample_tenant, sample_user):
        from models.login_history import LoginHistory

        failed = LoginHistory(user_id=sample_user.id, username=sample_user.username, success=False)
        db_session.add(failed)
        db_session.flush()

        page = OwnerOpsService.login_history_pagination(1, sample_tenant.id, sample_user.id, "false")
        assert failed in page.items
        assert all(not item.success for item in page.items)

    def test_users_scoped_by_tenant_ordered_by_username(self, db_session, sample_tenant, sample_role):
        from models import User

        u2 = User(
            username=f"aaa-{_uid()}",
            email=f"aaa-{_uid()}@example.com",
            full_name="A",
            tenant_id=sample_tenant.id,
            role_id=sample_role.id,
            is_active=True,
        )
        u2.set_password("pw123456")
        inactive = User(
            username=f"zzz-{_uid()}",
            email=f"zzz-{_uid()}@example.com",
            full_name="Z",
            tenant_id=sample_tenant.id,
            role_id=sample_role.id,
            is_active=False,
        )
        inactive.set_password("pw123456")
        db_session.add_all([u2, inactive])
        db_session.flush()

        users = OwnerOpsService.login_history_users(sample_tenant.id)
        ids = {u.id for u in users}
        assert u2.id in ids
        assert inactive.id not in ids
        assert all(u.tenant_id == sample_tenant.id for u in users)
        usernames = [u.username for u in users]
        assert usernames == sorted(usernames)

    def test_stats_count_created_rows(self, db_session, sample_tenant, sample_user):
        from models.login_history import LoginHistory

        before = OwnerOpsService.login_history_stats(sample_tenant.id)
        ok = LoginHistory(user_id=sample_user.id, username=sample_user.username, success=True)
        bad = LoginHistory(user_id=sample_user.id, username=sample_user.username, success=False)
        db_session.add_all([ok, bad])
        db_session.flush()

        after = OwnerOpsService.login_history_stats(sample_tenant.id)
        assert after["total_logins"] == before["total_logins"] + 1
        assert after["failed_logins"] == before["failed_logins"] + 1


# ── security alerts ──────────────────────────────────────────────────────────


class TestSecurityAlerts:
    def test_pagination_excludes_resolved_and_filters_severity(self, db_session):
        from models.security_alert import SecurityAlert

        open_high = SecurityAlert(alert_type="brute_force", severity="high", title="t1", is_resolved=False)
        resolved = SecurityAlert(alert_type="brute_force", severity="high", title="t2", is_resolved=True)
        open_low = SecurityAlert(alert_type="scan", severity="low", title="t3", is_resolved=False)
        db_session.add_all([open_high, resolved, open_low])
        db_session.flush()

        page = OwnerOpsService.security_alerts_pagination(1, None)
        ids = {a.id for a in page.items}
        assert open_high.id in ids and open_low.id in ids
        assert resolved.id not in ids

        high_only = OwnerOpsService.security_alerts_pagination(1, "high")
        high_ids = {a.id for a in high_only.items}
        assert open_high.id in high_ids
        assert open_low.id not in high_ids

    def test_stats_delta(self, db_session):
        from models.security_alert import SecurityAlert

        before = OwnerOpsService.security_alert_stats()
        db_session.add_all(
            [
                SecurityAlert(alert_type="x", severity="critical", title="c", is_resolved=False),
                SecurityAlert(alert_type="x", severity="high", title="h", is_resolved=False),
                SecurityAlert(alert_type="x", severity="high", title="hr", is_resolved=True),
            ]
        )
        db_session.flush()

        after = OwnerOpsService.security_alert_stats()
        assert after["unresolved"] == before["unresolved"] + 2
        assert after["critical"] == before["critical"] + 1
        assert after["high"] == before["high"] + 1

    def test_get_security_alert_or_404(self, db_session):
        from models.security_alert import SecurityAlert

        alert = SecurityAlert(alert_type="x", severity="low", title="t", is_resolved=False)
        db_session.add(alert)
        db_session.flush()

        assert OwnerOpsService.get_security_alert_or_404(alert.id).id == alert.id
        with pytest.raises(NotFound):
            OwnerOpsService.get_security_alert_or_404(999999999)


# ── api keys / users ─────────────────────────────────────────────────────────


class TestApiKeysAndUsers:
    def test_list_api_keys_newest_first(self, db_session):
        from models.api_key import APIKey

        old = APIKey(name="old-" + _uid(), key="k" + _uid() * 4, service="sms")
        db_session.add(old)
        db_session.flush()
        new = APIKey(name="new-" + _uid(), key="j" + _uid() * 4, service="sms")
        db_session.add(new)
        db_session.flush()

        keys = OwnerOpsService.list_api_keys()
        key_ids = [k.id for k in keys]
        assert key_ids.index(new.id) < key_ids.index(old.id)

    def test_get_api_key_or_404(self, db_session):
        from models.api_key import APIKey

        key = APIKey(name="n-" + _uid(), key="q" + _uid() * 4, service="sms")
        db_session.add(key)
        db_session.flush()

        assert OwnerOpsService.get_api_key_or_404(key.id).id == key.id
        with pytest.raises(NotFound):
            OwnerOpsService.get_api_key_or_404(999999999)

    def test_get_users_by_ids(self, db_session, sample_tenant, sample_user, sample_role):
        from models.user import User

        extra = User(
            username=f"u-{_uid()}",
            email=f"u-{_uid()}@example.com",
            full_name="U",
            tenant_id=sample_tenant.id,
            role_id=sample_role.id,
        )
        extra.set_password("pw123456")
        db_session.add(extra)
        db_session.flush()

        found = OwnerOpsService.get_users_by_ids([sample_user.id, extra.id])
        assert {u.id for u in found} >= {sample_user.id, extra.id}
        assert OwnerOpsService.get_users_by_ids([]) == []


# ── card vault ───────────────────────────────────────────────────────────────


class TestCardVault:
    def _card(self, db_session, tenant_id, customer_id, card_type="visa", active=True, usage=3):
        from models import CardVault

        card = CardVault(
            tenant_id=tenant_id,
            customer_id=customer_id,
            card_hash="h" + _uid() * 4,
            card_number_encrypted=b"x",
            cardholder_name_encrypted=b"y",
            card_type=card_type,
            last_four="1234",
            is_active=active,
            usage_count=usage,
        )
        db_session.add(card)
        db_session.flush()
        return card

    def test_context_scopes_and_counts(self, db_session, sample_tenant, sample_customer):
        card = self._card(db_session, sample_tenant.id, sample_customer.id, usage=7)

        ctx = OwnerOpsService.card_vault_context(1, None, sample_tenant.id)
        assert card.id in [c.id for c in ctx["pagination"].items]
        assert ctx["stats"]["total_cards"] >= 1
        assert ctx["stats"]["total_usage"] >= 7
        assert ctx["stats"]["visa_count"] >= 1
        assert ctx["stats"]["mastercard_count"] >= 0

        scoped = OwnerOpsService.card_vault_context(1, sample_customer.id, sample_tenant.id)
        assert all(c.customer_id == sample_customer.id for c in scoped["pagination"].items)

    def test_inactive_cards_excluded(self, db_session, sample_tenant, sample_customer):
        self._card(db_session, sample_tenant.id, sample_customer.id, active=False)
        ctx = OwnerOpsService.card_vault_context(1, sample_customer.id, sample_tenant.id)
        assert all(c.is_active for c in ctx["pagination"].items)

    def test_get_card_or_404(self, db_session, sample_tenant, sample_customer):
        card = self._card(db_session, sample_tenant.id, sample_customer.id)
        assert OwnerOpsService.get_card_or_404(card.id).id == card.id
        with pytest.raises(NotFound):
            OwnerOpsService.get_card_or_404(999999999)


# ── data cleanup / maintenance audit logs ────────────────────────────────────


class TestDataCleanupAndMaintenanceLogs:
    def test_data_cleanup_stats_keys(self, db_session):
        stats = OwnerOpsService.data_cleanup_stats()
        assert set(stats) == {"old_logs", "old_archived"}
        assert isinstance(stats["old_logs"], int)
        assert isinstance(stats["old_archived"], int)

    def test_delete_old_audit_logs_respects_cutoff(self, db_session, sample_tenant):
        from models import AuditLog

        stale = AuditLog(
            tenant_id=sample_tenant.id, action="legacy_import", created_at=datetime.now(UTC) - timedelta(days=365)
        )
        fresh = AuditLog(tenant_id=sample_tenant.id, action="legacy_import", created_at=datetime.now(UTC))
        db_session.add_all([stale, fresh])
        db_session.flush()

        deleted = OwnerOpsService.delete_old_audit_logs(datetime.now(UTC) - timedelta(days=90))
        assert deleted >= 1
        remaining = AuditLog.query.filter(AuditLog.action == "legacy_import").all()
        remaining_ids = {a.id for a in remaining}
        assert stale.id not in remaining_ids
        assert fresh.id in remaining_ids

    def test_delete_old_archived_records_zero_with_old_cutoff(self, db_session):
        deleted = OwnerOpsService.delete_old_archived_records(datetime.now(UTC) - timedelta(days=100000))
        assert deleted == 0

    def test_recent_maintenance_audit_logs_filters_actions(self, db_session, sample_tenant):
        from models import AuditLog

        match = AuditLog(tenant_id=sample_tenant.id, action="fix_cost_centers", created_at=datetime.now(UTC))
        other = AuditLog(tenant_id=sample_tenant.id, action="something_else", created_at=datetime.now(UTC))
        db_session.add_all([match, other])
        db_session.flush()

        logs = OwnerOpsService.recent_maintenance_audit_logs()
        actions = {log.action for log in logs}
        assert "fix_cost_centers" in actions or "rebuild_gl_tree" in actions
        assert "something_else" not in actions
        assert len(logs) <= 20


# ── exchange rates / warehouse (tenant-scoped settings lookups) ──────────────


class TestSettingsLookups:
    @staticmethod
    def _second_tenant(db_session):
        from models import Tenant

        tenant = Tenant(name=f"T-{_uid()}", name_ar=f"مستأجر-{_uid()}", slug=f"t-{_uid()}", is_active=True)
        db_session.add(tenant)
        db_session.flush()
        return tenant

    def test_find_exchange_rate_record_scopes_tenant(self, db_session, sample_tenant):
        from models.exchange_rate_record import ExchangeRateRecord

        rec = ExchangeRateRecord(
            tenant_id=sample_tenant.id,
            from_currency="USD",
            to_currency="AED",
            rate=Decimal("3.6725"),
            effective_date=date.today(),
        )
        db_session.add(rec)
        db_session.flush()

        other = self._second_tenant(db_session)
        assert OwnerOpsService.find_exchange_rate_record(rec.id, sample_tenant.id).id == rec.id
        assert OwnerOpsService.find_exchange_rate_record(rec.id, other.id) is None

    def test_recent_exchange_rate_records_ordering(self, db_session, sample_tenant):
        from models.exchange_rate_record import ExchangeRateRecord

        older = ExchangeRateRecord(
            tenant_id=sample_tenant.id,
            from_currency="EUR",
            to_currency="AED",
            rate=Decimal("4.0"),
            effective_date=date.today() - timedelta(days=5),
            created_at=datetime.now(UTC) - timedelta(days=5),
        )
        newer = ExchangeRateRecord(
            tenant_id=sample_tenant.id,
            from_currency="EUR",
            to_currency="AED",
            rate=Decimal("4.1"),
            effective_date=date.today(),
            created_at=datetime.now(UTC),
        )
        db_session.add_all([older, newer])
        db_session.flush()

        records = OwnerOpsService.recent_exchange_rate_records(sample_tenant.id)
        rec_ids = [r.id for r in records]
        assert rec_ids.index(newer.id) < rec_ids.index(older.id)

    def test_warehouse_in_tenant_scopes(self, db_session, online_warehouse):
        other = self._second_tenant(db_session)
        found = OwnerOpsService.warehouse_in_tenant(online_warehouse.id, online_warehouse.tenant_id)
        assert found.id == online_warehouse.id
        assert OwnerOpsService.warehouse_in_tenant(online_warehouse.id, other.id) is None


# ── landlord dashboard (super-admin) ─────────────────────────────────────────


class TestLandlordDashboardContext:
    def test_context_shape_and_package_inclusion(self, db_session, sample_tenant):
        from models.package import Package

        pkg = Package(
            name_ar="باقة",
            name_en=f"Pkg {_uid()}",
            slug=f"pkg-{_uid()}",
            price=50.0,
            is_active=True,
            sort_order=1,
        )
        db_session.add(pkg)
        db_session.flush()

        ctx = OwnerOpsService.landlord_dashboard_context()
        assert set(ctx) == {"tenants", "user_counts", "branch_counts", "admin_emails", "packages"}
        assert any(t.id == sample_tenant.id for t in ctx["tenants"])
        assert any(p.id == pkg.id for p in ctx["packages"])
        assert isinstance(ctx["user_counts"], dict)
        assert isinstance(ctx["branch_counts"], dict)

    def test_get_tenant_and_package(self, db_session, sample_tenant):
        from models.package import Package

        pkg = Package(
            name_ar="باقة",
            name_en=f"Pkg {_uid()}",
            slug=f"pkg-{_uid()}",
            price=10.0,
            is_active=True,
        )
        db_session.add(pkg)
        db_session.flush()

        assert OwnerOpsService.get_tenant(sample_tenant.id).id == sample_tenant.id
        assert OwnerOpsService.get_tenant(999999999) is None
        assert OwnerOpsService.get_package(pkg.id).id == pkg.id
        assert OwnerOpsService.get_package(999999999) is None
