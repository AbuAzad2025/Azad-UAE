from __future__ import annotations

import json


from models.print_history import PrintHistory


class TestPrintHistory:
    def test_repr(self, sample_tenant, sample_user):
        entry = PrintHistory(
            tenant_id=sample_tenant.id,
            user_id=sample_user.id,
            document_type="invoice",
            document_id=100,
            action="print",
        )
        text = repr(entry)
        assert "invoice" in text
        assert "100" in text
        assert str(sample_user.id) in text

    def test_meta_get_set_roundtrip(self, sample_tenant):
        entry = PrintHistory(
            tenant_id=sample_tenant.id,
            document_type="receipt",
            document_id=1,
        )
        entry.meta = {"copies": 2, "printer": "main"}
        assert entry.meta == {"copies": 2, "printer": "main"}
        assert json.loads(entry.metadata_json)["copies"] == 2

    def test_meta_empty_when_no_json(self, sample_tenant):
        entry = PrintHistory(
            tenant_id=sample_tenant.id,
            document_type="label",
            document_id=2,
        )
        assert entry.meta == {}

    def test_meta_invalid_json_returns_empty(self, sample_tenant):
        entry = PrintHistory(
            tenant_id=sample_tenant.id,
            document_type="label",
            document_id=3,
        )
        entry.metadata_json = "not-json"
        assert entry.meta == {}

    def test_meta_set_none_clears_json(self, sample_tenant):
        entry = PrintHistory(
            tenant_id=sample_tenant.id,
            document_type="label",
            document_id=4,
        )
        entry.meta = {"a": 1}
        entry.meta = None
        assert entry.metadata_json is None
