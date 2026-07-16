"""AuditLog model — display labels and serialization."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from models.audit import AuditLog


class TestAuditLogModel:
    def test_repr(self):
        log = AuditLog()
        log.action = 'create'
        log.table_name = 'sales'
        assert 'create' in repr(log)

    def test_get_action_display_known_ar(self):
        log = AuditLog()
        log.action = 'update'
        assert log.get_action_display() == 'تعديل'
        assert log.get_action_display('en') == 'Update'

    def test_get_action_display_unknown_falls_back(self):
        log = AuditLog()
        log.action = 'archive'
        assert log.get_action_display('fr') == 'archive'

    def test_to_dict_system_user_when_no_user(self):
        log = AuditLog()
        log.id = 1
        log.action = 'login'
        log.table_name = 'users'
        log.record_id = 5
        log.created_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
        log.ip_address = '127.0.0.1'
        log.user = None
        data = log.to_dict()
        assert data['user'] == 'System'
        assert data['action'] == 'login'
        assert '2025-06-01' in data['created_at']

    def test_to_dict_with_username(self):
        log = AuditLog()
        log.id = 2
        log.action = 'export'
        log.table_name = 'reports'
        log.record_id = None
        log.created_at = datetime(2025, 6, 2, tzinfo=timezone.utc)
        log.ip_address = None
        log.user = MagicMock(username='admin')
        assert log.to_dict()['user'] == 'admin'
