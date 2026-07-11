"""Archive service — soft/hard delete, restore integrity, aged cleanup."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


class TestArchiveRecord:
    """archive_record — tenant guard, commit rollback, flush path."""

    def test_archives_via_to_dict(self, app, mocker):
        record = MagicMock()
        record.id = 10
        record.tenant_id = 1
        record.to_dict.return_value = {'id': 10, 'name': 'Sale'}

        mock_user = MagicMock()
        mock_user.is_authenticated = True
        mock_user.id = 5
        mocker.patch('services.archive_service.current_user', mock_user)
        mock_session = mocker.patch('services.archive_service.db.session')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()

        from services.archive_service import ArchiveService

        with app.app_context():
            archived = ArchiveService.archive_record('sales', record, reason='audit')

        assert archived.tenant_id == 1
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    def test_missing_tenant_id_raises(self, app, mocker):
        class Row:
            id = 1
            tenant_id = None
            __table__ = MagicMock(columns=[])

        record = Row()

        mocker.patch('services.archive_service.current_user', MagicMock(is_authenticated=False))
        mocker.patch('services.archive_service.db.session')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()

        from services.archive_service import ArchiveService

        with app.app_context():
            with pytest.raises(ValueError, match='no tenant_id'):
                ArchiveService.archive_record('sales', record)

    def test_commit_failure_rolls_back(self, app, mocker):
        record = MagicMock(id=2, tenant_id=1)
        record.to_dict.return_value = {'id': 2}
        mocker.patch('services.archive_service.current_user', MagicMock(is_authenticated=False))
        mock_session = mocker.patch('services.archive_service.db.session')
        mock_session.flush.side_effect = RuntimeError('db down')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()

        from services.archive_service import ArchiveService

        with app.app_context():
            with pytest.raises(RuntimeError):
                ArchiveService.archive_record('sales', record)
        mock_session.flush.assert_called()

    def test_deferred_commit_flushes_only(self, app, mocker):
        record = MagicMock(id=3, tenant_id=1)
        record.to_dict.return_value = {'id': 3}
        mocker.patch('services.archive_service.current_user', MagicMock(is_authenticated=False))
        mock_session = mocker.patch('services.archive_service.db.session')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()

        from services.archive_service import ArchiveService

        with app.app_context():
            ArchiveService.archive_record('payments', record)
        mock_session.flush.assert_called_once()
        mock_session.commit.assert_not_called()


class TestDeletePaths:
    """soft_delete / hard_delete — referential safety via archive-first."""

    def test_soft_delete_deactivates_record(self, app, mocker):
        record = MagicMock(is_active=True)
        mock_session = mocker.patch('services.archive_service.db.session')

        from services.archive_service import ArchiveService

        with app.app_context():
            ArchiveService.soft_delete(record)
        assert record.is_active is False
        mock_session.flush.assert_called_once()

    def test_soft_delete_rollback_on_failure(self, app, mocker):
        record = MagicMock()
        mock_session = mocker.patch('services.archive_service.db.session')
        mock_session.flush.side_effect = RuntimeError('lock')

        from services.archive_service import ArchiveService

        with app.app_context():
            with pytest.raises(RuntimeError):
                ArchiveService.soft_delete(record)
        mock_session.flush.assert_called_once()

    def test_hard_delete_archives_then_deletes(self, app, mocker):
        record = MagicMock(id=9, tenant_id=1)
        record.to_dict.return_value = {'id': 9}
        mocker.patch('services.archive_service.current_user', MagicMock(is_authenticated=False))
        mocker.patch('services.archive_service.current_app').logger = MagicMock()
        mock_session = mocker.patch('services.archive_service.db.session')

        from services.archive_service import ArchiveService

        with app.app_context():
            ArchiveService.hard_delete('sales', record, archive_first=True)

        mock_session.delete.assert_called_once_with(record)
        mock_session.flush.assert_called()

    def test_hard_delete_interrupt_rolls_back(self, app, mocker):
        record = MagicMock(id=9, tenant_id=1)
        record.to_dict.return_value = {'id': 9}
        mocker.patch('services.archive_service.current_user', MagicMock(is_authenticated=False))
        mocker.patch('services.archive_service.current_app').logger = MagicMock()
        mock_session = mocker.patch('services.archive_service.db.session')
        mock_session.flush.side_effect = RuntimeError('interrupt')

        from services.archive_service import ArchiveService

        with app.app_context():
            with pytest.raises(RuntimeError):
                ArchiveService.hard_delete('sales', record)
        mock_session.flush.assert_called()


class TestRestoreAndQuery:
    """restore_record — tenant partition lock; queries and aged cleanup."""

    def test_restore_tenant_mismatch_blocked(self, app, mocker):
        archived = MagicMock(table_name='sales', tenant_id=2, record_id=100)
        mocker.patch('utils.tenanting.get_active_tenant_id', return_value=1)
        mocker.patch('services.archive_service.current_user', MagicMock())
        mocker.patch('services.archive_service.ArchiveService._init_archive_model_map')
        mocker.patch('services.archive_service.ArchiveService.ARCHIVE_MODEL_MAP', {'sales': MagicMock()})
        mocker.patch('services.archive_service.db.session')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()

        from services.archive_service import ArchiveService

        with app.app_context():
            with pytest.raises(PermissionError, match='tenant mismatch'):
                ArchiveService.restore_record(archived)

    def test_restore_reactivates_existing_row(self, app, mocker):
        archived = MagicMock(table_name='sales', tenant_id=1, record_id=50)
        existing = MagicMock(is_active=False)
        model = MagicMock()
        model.query.get.return_value = existing

        mocker.patch('utils.tenanting.get_active_tenant_id', return_value=1)
        mocker.patch('services.archive_service.current_user', MagicMock())
        mocker.patch('services.archive_service.ArchiveService.ARCHIVE_MODEL_MAP', {'sales': model})
        mock_session = mocker.patch('services.archive_service.db.session')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()

        from services.archive_service import ArchiveService

        with app.app_context():
            result = ArchiveService.restore_record(archived)

        assert result is existing
        assert existing.is_active is True
        mock_session.flush.assert_called_once()

    def test_get_archived_records_filters_table(self, app, mocker):
        from models import ArchivedRecord

        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = [MagicMock()]
        mocker.patch.object(
            ArchivedRecord, 'query', new_callable=mocker.PropertyMock, return_value=mock_q,
        )

        from services.archive_service import ArchiveService

        with app.app_context():
            rows = ArchiveService.get_archived_records(table_name='sales', limit=10)
        assert len(rows) == 1
        mock_q.filter_by.assert_called_with(table_name='sales')

    def test_cleanup_old_archives_three_year_cutoff(self, app, mocker):
        from models import ArchivedRecord

        old = MagicMock()
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.all.return_value = [old, old]
        mocker.patch.object(
            ArchivedRecord, 'query', new_callable=mocker.PropertyMock, return_value=mock_q,
        )
        mock_session = mocker.patch('services.archive_service.db.session')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()

        from services.archive_service import ArchiveService

        with app.app_context():
            count = ArchiveService.cleanup_old_archives(days=365 * 3)

        assert count == 2
        assert mock_session.delete.call_count == 2
        mock_session.commit.assert_called_once()

    def test_archive_without_to_dict_uses_columns(self, app, mocker):
        class Row:
            id = 7
            tenant_id = 1
            name = 'Legacy'

            def __init__(self):
                col = MagicMock()
                col.name = 'name'
                self.__table__ = MagicMock(columns=[col])

        record = Row()
        mocker.patch('services.archive_service.current_user', MagicMock(is_authenticated=False))
        mocker.patch('services.archive_service.db.session')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()
        from services.archive_service import ArchiveService
        with app.app_context():
            archived = ArchiveService.archive_record('sales', record)
        assert archived.tenant_id == 1

    def test_archive_failure_rolls_back_on_outer_error(self, app, mocker):
        record = MagicMock(id=1, tenant_id=1)
        record.to_dict.side_effect = RuntimeError('serialize fail')
        mocker.patch('services.archive_service.current_user', MagicMock(is_authenticated=False))
        mock_session = mocker.patch('services.archive_service.db.session')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()
        from services.archive_service import ArchiveService
        with app.app_context():
            with pytest.raises(RuntimeError):
                ArchiveService.archive_record('sales', record)
        mock_session.add.assert_not_called()

    def test_restore_unknown_table_raises(self, app, mocker):
        archived = MagicMock(table_name='unknown_tbl', tenant_id=1, record_id=1)
        mocker.patch('utils.tenanting.get_active_tenant_id', return_value=1)
        mocker.patch('services.archive_service.current_user', MagicMock())
        mocker.patch('services.archive_service.db.session')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()
        from services.archive_service import ArchiveService
        with app.app_context():
            with pytest.raises(ValueError, match='Model not found'):
                ArchiveService.restore_record(archived)

    def test_restore_missing_row_raises(self, app, mocker):
        archived = MagicMock(table_name='sales', tenant_id=1, record_id=404)
        model = MagicMock()
        model.query.get.return_value = None
        mocker.patch('utils.tenanting.get_active_tenant_id', return_value=1)
        mocker.patch('services.archive_service.current_user', MagicMock())
        mocker.patch('services.archive_service.ArchiveService.ARCHIVE_MODEL_MAP', {'sales': model})
        mocker.patch('services.archive_service.db.session')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()
        from services.archive_service import ArchiveService
        with app.app_context():
            with pytest.raises(ValueError, match='Record not found'):
                ArchiveService.restore_record(archived)

    def test_init_archive_model_map_populates(self, app):
        from services.archive_service import ArchiveService
        ArchiveService.ARCHIVE_MODEL_MAP = {k: None for k in ArchiveService.ARCHIVE_MODEL_MAP}
        with app.app_context():
            ArchiveService._init_archive_model_map()
        assert ArchiveService.ARCHIVE_MODEL_MAP['sales'] is not None

    def test_get_archived_records_query(self, app, mocker):
        from models import ArchivedRecord
        mock_q = MagicMock()
        mock_q.filter_by.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mocker.patch.object(ArchivedRecord, 'query', new_callable=mocker.PropertyMock, return_value=mock_q)
        from services.archive_service import ArchiveService
        with app.app_context():
            ArchiveService.get_archived_records_query(table_name='payments')
        mock_q.filter_by.assert_called_with(table_name='payments')

    def test_cleanup_old_archives_commit_failure(self, app, mocker):
        from models import ArchivedRecord
        mock_q = MagicMock()
        mock_q.filter.return_value.all.return_value = [MagicMock()]
        mocker.patch.object(ArchivedRecord, 'query', new_callable=mocker.PropertyMock, return_value=mock_q)
        mock_session = mocker.patch('services.archive_service.db.session')
        mock_session.commit.side_effect = RuntimeError('lock')
        mocker.patch('services.archive_service.current_app').logger = MagicMock()
        from services.archive_service import ArchiveService
        with app.app_context():
            with pytest.raises(RuntimeError):
                ArchiveService.cleanup_old_archives(days=30)
        mock_session.rollback.assert_called()
