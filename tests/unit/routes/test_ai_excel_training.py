"""Unit tests for the Excel training hook — tenant-scoped, logged, flush-only."""

from __future__ import annotations

import pandas as pd


def _frame():
    return pd.DataFrame([{"name": "فلتر", "price": 10.0}, {"name": "زيت", "price": 20.0}])


class TestTrainAiFromExcel:
    def test_learns_tenant_scoped_summary(self, db_session, sample_tenant):
        from models.ai import AiMemory
        from routes.ai_routes.assistant import _train_ai_from_excel

        result = _train_ai_from_excel(_frame(), 2, 0, user_id=5, tenant_id=sample_tenant.id)
        assert result["learned"] is True
        assert result["rows"] == 2
        row = AiMemory.query.filter_by(tenant_id=sample_tenant.id).first()
        assert row is not None
        assert "2" in row.key

    def test_other_tenant_untouched(self, db_session, sample_tenant):
        from models.ai import AiMemory
        from routes.ai_routes.assistant import _train_ai_from_excel

        _train_ai_from_excel(_frame(), 1, 1, user_id=5, tenant_id=sample_tenant.id)
        assert AiMemory.query.filter_by(tenant_id=sample_tenant.id + 999).count() == 0
