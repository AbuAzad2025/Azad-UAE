"""Unit tests for services/training_importer.py — JSON/Excel ingestion."""

from __future__ import annotations

import json

import pytest

from services import training_importer as importer_mod
from services.training_importer import TrainingImporter


@pytest.fixture
def importer(tmp_path):
    imp = TrainingImporter(upload_folder=str(tmp_path))
    return imp


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


class TestImportFromJson:
    def test_list_payload(self, db_session, sample_tenant, importer, tmp_path):
        fp = _write_json(
            tmp_path / "t.json",
            [
                {"question": "What is VAT?", "answer": "5% in UAE", "category": "tax"},
                {"question": "Empty answer", "answer": ""},
            ],
        )
        result = importer.import_from_json(fp, sample_tenant.id)
        assert result["success"] is True
        assert result["processed"] == 1
        assert result["total"] == 2
        assert result["errors"] == 1

    def test_training_data_key(self, db_session, sample_tenant, importer, tmp_path):
        fp = _write_json(
            tmp_path / "t2.json",
            {"training_data": [{"question": "Q1?", "answer": "A1"}]},
        )
        result = importer.import_from_json(fp, sample_tenant.id)
        assert result["success"] is True
        assert result["processed"] == 1

    def test_qa_pairs_key(self, db_session, sample_tenant, importer, tmp_path):
        fp = _write_json(tmp_path / "t3.json", {"qa_pairs": [{"question": "Q2?", "answer": "A2"}]})
        result = importer.import_from_json(fp, sample_tenant.id)
        assert result["success"] is True
        assert result["processed"] == 1

    def test_invalid_json(self, db_session, sample_tenant, importer, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        result = importer.import_from_json(str(bad), sample_tenant.id)
        assert result["success"] is False
        assert "Invalid JSON" in result["error"]

    def test_batch_record_created(self, db_session, sample_tenant, importer, tmp_path):
        from models.ai_training_advanced import AiTrainingBatch

        fp = _write_json(tmp_path / "t4.json", [{"question": "Q?", "answer": "A"}])
        result = importer.import_from_json(fp, sample_tenant.id)
        batch = db_session.get(AiTrainingBatch, result["batch_id"])
        assert batch is not None
        assert batch.status in ("completed", "completed_with_errors")
        assert batch.file_type == "json"

    def test_tenant_isolation(self, db_session, sample_tenant, importer, tmp_path):
        from models.ai import AiMemory
        from tests.factories import TenantFactory
        from utils.tenanting import tenant_query

        other = TenantFactory()
        db_session.flush()
        fp = _write_json(tmp_path / "t5.json", [{"question": "Iso Q?", "answer": "Iso A"}])
        importer.import_from_json(fp, sample_tenant.id)
        mine = tenant_query(AiMemory).filter(AiMemory.tenant_id == sample_tenant.id).all()
        theirs = tenant_query(AiMemory).filter(AiMemory.tenant_id == other.id).all()
        assert any(m.key == "iso q?" for m in mine)
        assert theirs == []


class TestImportFromExcel:
    def test_basic_excel(self, db_session, sample_tenant, importer, tmp_path):
        import pandas as pd

        fp = str(tmp_path / "t.xlsx")
        pd.DataFrame(
            [
                {"question": "Excel Q?", "answer": "Excel A", "category": "general"},
                {"question": "No answer", "answer": ""},
            ]
        ).to_excel(fp, index=False)
        result = importer.import_from_excel(fp, sample_tenant.id)
        assert result["success"] is True
        assert result["processed"] == 1
        assert result["total"] == 2

    def test_missing_columns(self, db_session, sample_tenant, importer, tmp_path):
        import pandas as pd

        fp = str(tmp_path / "bad.xlsx")
        pd.DataFrame([{"foo": "bar"}]).to_excel(fp, index=False)
        result = importer.import_from_excel(fp, sample_tenant.id)
        assert result["success"] is False
        assert "question" in result["error"]


class TestSecurity:
    def test_validate_file_security(self, importer):
        assert importer.validate_file_security("data.json") is True
        assert importer.validate_file_security("data.xlsx") is True
        assert importer.validate_file_security("data.xls") is True
        assert importer.validate_file_security("evil.exe") is False
        assert importer.validate_file_security("evil.py") is False

    def test_safe_filename(self, importer):
        assert importer.get_safe_filename("../../etc/passwd") == "passwd"
        assert len(importer.get_safe_filename("a" * 500)) <= 255

    def test_module_singleton_importable(self):
        assert importer_mod.training_importer is not None
