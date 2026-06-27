from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from utils import gl_tenant as gt


class _Col:
    def __eq__(self, other):
        return self

    def __ge__(self, other):
        return self


class TestActiveTenantId:
    def test_delegates_to_get_active_tenant_id(self):
        user = MagicMock()
        with patch('utils.gl_tenant.get_active_tenant_id', return_value=5) as g:
            assert gt.active_tenant_id(user) == 5
            g.assert_called_once_with(user)


class TestScopeGlAccounts:
    def test_filters_when_tenant_present(self):
        q = MagicMock()
        model = type('GLAccount', (), {'tenant_id': _Col()})
        with patch('models.GLAccount', model):
            result = gt.scope_gl_accounts(q, tenant_id=3)
        q.filter.assert_called_once()
        assert result is q.filter.return_value

    def test_returns_query_when_no_tenant(self):
        q = MagicMock()
        with patch('utils.gl_tenant.active_tenant_id', return_value=None):
            assert gt.scope_gl_accounts(q) is q


class TestScopeJournalEntries:
    def test_filters_when_tenant_present(self):
        q = MagicMock()
        model = type('GLJournalEntry', (), {'tenant_id': _Col()})
        with patch('models.GLJournalEntry', model, create=True):
            result = gt.scope_journal_entries(q, tenant_id=2)
        q.filter.assert_called_once()

    def test_returns_query_when_no_tenant(self):
        q = MagicMock()
        with patch('utils.gl_tenant.active_tenant_id', return_value=None):
            assert gt.scope_journal_entries(q) is q


class TestGetGlAccountByCode:
    def test_scopes_by_tenant(self):
        account = MagicMock()
        q = MagicMock()
        q.filter_by.return_value = q
        q.first.return_value = account
        model = MagicMock()
        model.query = q
        with patch('models.GLAccount', model):
            result = gt.get_gl_account_by_code('1000', tenant_id=9)
        assert result is account
        q.filter_by.assert_any_call(code='1000')
        q.filter_by.assert_any_call(tenant_id=9)

    def test_without_tenant(self):
        q = MagicMock()
        q.filter_by.return_value = q
        q.first.return_value = None
        model = MagicMock()
        model.query = q
        with patch('models.GLAccount', model), patch('utils.gl_tenant.active_tenant_id', return_value=None):
            assert gt.get_gl_account_by_code('2000') is None


class TestReverseDocumentGl:
    def test_reverses_single_type(self):
        with patch('services.gl_service.GLService') as GLService:
            gt.reverse_document_gl('sale', 10, 'reverse', tenant_id=1)
            GLService.reverse_entry.assert_called_once_with(
                reference_type='sale',
                reference_id=10,
                description='reverse',
                tenant_id=1,
            )

    def test_reverses_multiple_types(self):
        with patch('services.gl_service.GLService') as GLService:
            gt.reverse_document_gl(['sale', 'payment'], 11, 'rev', tenant_id=2)
            assert GLService.reverse_entry.call_count == 2


class TestDefaultReportDateRange:
    def test_returns_iso_range(self):
        start, end = gt.default_report_date_range(days=30)
        assert len(start) == 10
        assert len(end) == 10
        assert start < end


class TestScopedModelQuery:
    def test_uses_tenant_query_when_model_has_tenant(self):
        model = MagicMock()
        scoped = MagicMock()
        with patch('utils.tenanting.model_has_tenant', return_value=True), \
             patch('utils.tenanting.tenant_query', return_value=scoped) as tq:
            assert gt.scoped_model_query(model, user=MagicMock()) is scoped
            tq.assert_called_once()

    def test_returns_plain_query_without_tenant(self):
        model = MagicMock()
        model.query = 'plain'
        with patch('utils.tenanting.model_has_tenant', return_value=False):
            assert gt.scoped_model_query(model) == 'plain'


class TestQueryHelpers:
    def test_gl_account_query(self):
        model = MagicMock()
        model.query = MagicMock()
        with patch('models.GLAccount', model), \
             patch('utils.gl_tenant.scope_gl_accounts', return_value='scoped') as scope:
            assert gt.gl_account_query(tenant_id=4) == 'scoped'

    def test_gl_entry_query(self):
        model = MagicMock()
        model.query = MagicMock()
        with patch('models.GLJournalEntry', model), \
             patch('utils.gl_tenant.scope_journal_entries', return_value='scoped') as scope:
            assert gt.gl_entry_query(tenant_id=4) == 'scoped'
