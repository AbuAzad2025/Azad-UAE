"""Document sequence — atomic numbering, tenant prefixes, reset intervals."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


class TestGetOrCreate:
    """get_or_create — tenant-scoped defaults and reuse."""

    def test_returns_existing_sequence(self, app, mocker):
        existing = MagicMock(id=1, code='sale', tenant_id=1)
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = existing
        mocker.patch('services.document_sequence_service.DocumentSequence.query', mock_q)

        from services.document_sequence_service import DocumentSequenceService
        with app.app_context():
            seq = DocumentSequenceService.get_or_create(1, 'sale')
        assert seq is existing

    def test_creates_sale_defaults(self, app, mocker):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch('services.document_sequence_service.DocumentSequence.query', mock_q)
        mock_session = mocker.patch('services.document_sequence_service.db.session')

        from services.document_sequence_service import DocumentSequenceService, DocumentSequence
        with app.app_context():
            seq = DocumentSequenceService.get_or_create(1, 'sale')

        mock_session.add.assert_called_once()
        assert seq.prefix == 'SALE'
        assert '{year}' in seq.pattern

    def test_unknown_code_uses_doc_fallback(self, app, mocker):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch('services.document_sequence_service.DocumentSequence.query', mock_q)
        mocker.patch('services.document_sequence_service.db.session')

        from services.document_sequence_service import DocumentSequenceService
        with app.app_context():
            seq = DocumentSequenceService.get_or_create(2, 'custom_doc')
        assert seq.prefix == 'DOC'


class TestNextNumber:
    """next_number — row lock, inactive guard, counter consumption."""

    def test_raises_when_sequence_inactive(self, app, mocker):
        seq = MagicMock(id=1, is_active=False, code='invoice')
        mocker.patch(
            'services.document_sequence_service.DocumentSequenceService.get_or_create',
            return_value=seq,
        )

        from services.document_sequence_service import DocumentSequenceService
        with app.app_context():
            with pytest.raises(ValueError, match='inactive'):
                DocumentSequenceService.next_number(1, 'invoice')

    def test_generates_number_under_lock(self, app, mocker):
        seq = MagicMock(id=5, is_active=True, code='payment')
        locked = MagicMock()
        locked.get_next_number.return_value = 'PAY-2026-0007'
        mocker.patch(
            'services.document_sequence_service.DocumentSequenceService.get_or_create',
            return_value=seq,
        )
        mock_session = mocker.patch('services.document_sequence_service.db.session')
        mock_session.query.return_value.filter_by.return_value.with_for_update.return_value.first.return_value = locked

        from services.document_sequence_service import DocumentSequenceService
        with app.app_context():
            number = DocumentSequenceService.next_number(1, 'payment', branch_code='DXB')

        assert number == 'PAY-2026-0007'
        locked.get_next_number.assert_called_once()
        mock_session.flush.assert_called()

    def test_lock_miss_raises(self, app, mocker):
        seq = MagicMock(id=5, is_active=True, code='receipt')
        mocker.patch(
            'services.document_sequence_service.DocumentSequenceService.get_or_create',
            return_value=seq,
        )
        mock_session = mocker.patch('services.document_sequence_service.db.session')
        mock_session.query.return_value.filter_by.return_value.with_for_update.return_value.first.return_value = None

        from services.document_sequence_service import DocumentSequenceService
        with app.app_context():
            with pytest.raises(ValueError, match='not found after lock'):
                DocumentSequenceService.next_number(1, 'receipt')


class TestPreview:
    """preview — no counter increment, pattern rendering."""

    def test_preview_does_not_increment_counter(self, app, mocker):
        from models.document_sequence import DocumentSequence
        seq = DocumentSequence(
            tenant_id=1,
            code='invoice',
            name='Invoice',
            prefix='INV',
            pattern='{prefix}-{year}-{counter:04d}',
            counter=42,
            counter_reset='year',
        )
        mocker.patch(
            'services.document_sequence_service.DocumentSequenceService.get_or_create',
            return_value=seq,
        )
        fixed_date = datetime(2026, 6, 15, tzinfo=timezone.utc)

        from services.document_sequence_service import DocumentSequenceService
        with app.app_context():
            preview = DocumentSequenceService.preview(1, 'invoice', branch_code='AUH', date=fixed_date)

        assert preview == 'INV-2026-0042'
        assert seq.counter == 42

    def test_yearly_reset_interval_on_model(self):
        from models.document_sequence import DocumentSequence
        seq = DocumentSequence(
            tenant_id=1, code='sale', name='Sale', prefix='SALE',
            pattern='{prefix}-{year}-{counter:04d}', counter=1, counter_reset='year',
        )
        old_date = datetime(2025, 12, 31, tzinfo=timezone.utc)
        new_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
        seq.updated_at = old_date
        number = seq.get_next_number(date=new_date)
        assert number.startswith('SALE-2026-')
        assert seq.counter == 2
