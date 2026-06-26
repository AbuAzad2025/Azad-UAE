from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from extensions import db
from models import GLJournalEntry
from utils.gl_reference_types import (
    GLRef,
    LEGACY_REF_MAP,
    delete_entries_by_ref,
    filter_entries_by_ref,
    normalize_ref_type,
    ref_variants,
)


class TestNormalizeRefType:
    def test_none_passthrough(self):
        assert normalize_ref_type(None) is None

    def test_empty_passthrough(self):
        assert normalize_ref_type('') == ''

    def test_legacy_mapping(self):
        assert normalize_ref_type('sale') == GLRef.SALE
        assert normalize_ref_type('cheque_receive') == GLRef.CHEQUE_RECEIVE

    def test_canonical_unchanged(self):
        assert normalize_ref_type(GLRef.PURCHASE) == GLRef.PURCHASE


class TestRefVariants:
    def test_canonical_variants(self):
        variants = ref_variants(GLRef.SALE)
        assert GLRef.SALE in variants
        assert 'sale' in variants

    def test_legacy_input(self):
        variants = ref_variants('sale_cogs')
        assert GLRef.SALE_COGS in variants

    def test_unknown_returns_self(self):
        assert ref_variants('UnknownRef') == ['UnknownRef']


class TestFilterEntriesByRef:
    def test_filters_by_variants(self):
        query = MagicMock()
        with patch('models.GLJournalEntry') as je:
            filter_entries_by_ref(query, GLRef.SALE)
        query.filter.assert_called_once()
        je.reference_type.in_.assert_called_once()


class TestDeleteEntriesByRef:
    def test_deletes_matching_entries(self, db_session, sample_tenant):
        entry = GLJournalEntry(
            tenant_id=sample_tenant.id,
            entry_number='JE-DEL-001',
            description='test',
            reference_type=GLRef.SALE,
            reference_id=42,
            currency='AED',
            exchange_rate=1,
            is_posted=True,
        )
        db_session.add(entry)
        db_session.flush()
        deleted = delete_entries_by_ref(42, GLRef.SALE, tenant_id=sample_tenant.id)
        assert deleted == 1

    def test_no_types_returns_zero(self):
        assert delete_entries_by_ref(1) == 0

    def test_tenant_scoped_delete(self, mocker):
        query = MagicMock()
        query.filter.return_value = query
        query.delete.return_value = 0
        mocker.patch(
            'models.GLJournalEntry.query',
            query,
        )
        deleted = delete_entries_by_ref(99, 'sale', tenant_id=1)
        assert deleted == 0
        assert query.filter.call_count >= 2
