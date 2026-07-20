"""Audit service — tenant-scoped logs, filtering, stats, tamper-resistant reads."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock


def _build_audit_mocks(mocker, items):
    """Wire AuditLog.query for get_audit_logs_data."""
    pag = MagicMock()
    pag.items = items

    query_mock = MagicMock()
    query_mock.filter_by.return_value = query_mock
    query_mock.filter.return_value = query_mock
    query_mock.order_by.return_value.paginate.return_value = pag
    query_mock.count.side_effect = [10, 2, 4, 3, 3]

    audit_log = mocker.patch("services.audit_service.AuditLog")
    audit_log.query = query_mock
    audit_log.created_at = MagicMock()

    user_q = MagicMock()
    user_q.filter_by.return_value.all.return_value = [MagicMock(id=1, username="admin")]
    User = mocker.patch("services.audit_service.User")
    User.query = user_q

    return query_mock


class TestAuditServiceGetLogs:
    """get_audit_logs_data — pagination, filters, tenant isolation."""

    def test_returns_items_pagination_stats_users(self, mocker):
        log1 = MagicMock(action="create", user_id=1, created_at=datetime.now(timezone.utc))
        _build_audit_mocks(mocker, [log1])

        from services.audit_service import AuditService

        items, pagination, stats, users = AuditService.get_audit_logs_data(
            tid=1,
            page=1,
            per_page=20,
            action=None,
            user_id=None,
        )
        assert items == [log1]
        assert pagination.items == [log1]
        assert stats["total"] == 10
        assert stats["today"] == 2
        assert len(users) == 1

    def test_action_filter_applied(self, mocker):
        query_mock = _build_audit_mocks(mocker, [])
        from services.audit_service import AuditService

        AuditService.get_audit_logs_data(tid=2, page=1, per_page=10, action="delete", user_id=None)
        query_mock.filter_by.assert_any_call(action="delete")

    def test_user_id_filter_applied(self, mocker):
        query_mock = _build_audit_mocks(mocker, [])
        from services.audit_service import AuditService

        AuditService.get_audit_logs_data(tid=2, page=1, per_page=10, action=None, user_id=42)
        query_mock.filter_by.assert_any_call(user_id=42)

    def test_tenant_isolation_on_primary_query(self, mocker):
        query_mock = _build_audit_mocks(mocker, [])
        from services.audit_service import AuditService

        AuditService.get_audit_logs_data(tid=7, page=1, per_page=50, action=None, user_id=None)
        query_mock.filter_by.assert_any_call(tenant_id=7)

    def test_pagination_error_out_false(self, mocker):
        query_mock = _build_audit_mocks(mocker, [])
        from services.audit_service import AuditService

        AuditService.get_audit_logs_data(tid=1, page=99, per_page=5, action=None, user_id=None)
        query_mock.order_by.return_value.paginate.assert_called_once_with(
            page=99,
            per_page=5,
            error_out=False,
        )

    def test_stats_include_action_breakdown(self, mocker):
        _build_audit_mocks(mocker, [])
        from services.audit_service import AuditService

        _, _, stats, _ = AuditService.get_audit_logs_data(1, 1, 20, None, None)
        assert stats["creates"] == 4
        assert stats["updates"] == 3
        assert stats["deletes"] == 3

    def test_users_scoped_to_tenant(self, mocker):
        _build_audit_mocks(mocker, [])
        User = mocker.patch("services.audit_service.User")
        from services.audit_service import AuditService

        AuditService.get_audit_logs_data(5, 1, 20, None, None)
        User.query.filter_by.assert_called_with(is_active=True, tenant_id=5)

    def test_combined_action_and_user_filters(self, mocker):
        query_mock = _build_audit_mocks(mocker, [])
        from services.audit_service import AuditService

        AuditService.get_audit_logs_data(1, 2, 15, action="update", user_id=9)
        query_mock.filter_by.assert_any_call(action="update")
        query_mock.filter_by.assert_any_call(user_id=9)


class TestAuditLogIntegrity:
    """Audit records are read-only via service — no mutation surface."""

    def test_service_exposes_no_write_methods(self):
        from services.audit_service import AuditService

        public = [m for m in dir(AuditService) if not m.startswith("_")]
        assert public == ["get_audit_logs_data"]

    def test_log_entries_returned_from_query(self, mocker):
        original = MagicMock(action="delete", tenant_id=1)
        _build_audit_mocks(mocker, [original])
        from services.audit_service import AuditService

        items, _, _, _ = AuditService.get_audit_logs_data(1, 1, 20, None, None)
        assert items[0] is original
        assert items[0].action == "delete"
