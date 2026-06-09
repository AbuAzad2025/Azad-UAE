"""Unit tests for scripts/maintenance/fix_schema_mismatches.py helpers."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from unittest.mock import MagicMock, patch


class FakeInspector:
    def __init__(self, columns=None, indexes=None, fks=None):
        self._columns = columns or []
        self._indexes = indexes or []
        self._fks = fks or []

    def get_columns(self, table_name):
        return [{"name": c} for c in self._columns]

    def get_indexes(self, table_name):
        return [{"name": n} for n in self._indexes]

    def get_foreign_keys(self, table_name):
        return [{"name": n} for n in self._fks]


class TestSchemaRepairHelpers:
    def test_column_exists_true(self):
        inspector = FakeInspector(columns=["tenant_id"])
        engine = MagicMock()
        with patch("scripts.maintenance.fix_schema_mismatches.inspect", return_value=inspector):
            with patch("scripts.maintenance.fix_schema_mismatches.db") as mock_db:
                mock_db.engine = engine
                from scripts.maintenance.fix_schema_mismatches import _column_exists
                assert _column_exists("card_vault", "tenant_id") is True

    def test_column_exists_false(self):
        inspector = FakeInspector(columns=["id"])
        engine = MagicMock()
        with patch("scripts.maintenance.fix_schema_mismatches.inspect", return_value=inspector):
            with patch("scripts.maintenance.fix_schema_mismatches.db") as mock_db:
                mock_db.engine = engine
                from scripts.maintenance.fix_schema_mismatches import _column_exists
                assert _column_exists("card_vault", "tenant_id") is False

    def test_index_exists_true(self):
        inspector = FakeInspector(indexes=["ix_card_vault_tenant_id"])
        engine = MagicMock()
        with patch("scripts.maintenance.fix_schema_mismatches.inspect", return_value=inspector):
            with patch("scripts.maintenance.fix_schema_mismatches.db") as mock_db:
                mock_db.engine = engine
                from scripts.maintenance.fix_schema_mismatches import _index_exists
                assert _index_exists("card_vault", "ix_card_vault_tenant_id") is True

    def test_index_exists_false(self):
        inspector = FakeInspector(indexes=[])
        engine = MagicMock()
        with patch("scripts.maintenance.fix_schema_mismatches.inspect", return_value=inspector):
            with patch("scripts.maintenance.fix_schema_mismatches.db") as mock_db:
                mock_db.engine = engine
                from scripts.maintenance.fix_schema_mismatches import _index_exists
                assert _index_exists("card_vault", "ix_card_vault_tenant_id") is False

    def test_fk_exists_true(self):
        inspector = FakeInspector(fks=["fk_card_vault_tenant_id"])
        engine = MagicMock()
        with patch("scripts.maintenance.fix_schema_mismatches.inspect", return_value=inspector):
            with patch("scripts.maintenance.fix_schema_mismatches.db") as mock_db:
                mock_db.engine = engine
                from scripts.maintenance.fix_schema_mismatches import _fk_exists
                assert _fk_exists("card_vault", "fk_card_vault_tenant_id") is True

    def test_fk_exists_false(self):
        inspector = FakeInspector(fks=[])
        engine = MagicMock()
        with patch("scripts.maintenance.fix_schema_mismatches.inspect", return_value=inspector):
            with patch("scripts.maintenance.fix_schema_mismatches.db") as mock_db:
                mock_db.engine = engine
                from scripts.maintenance.fix_schema_mismatches import _fk_exists
                assert _fk_exists("card_vault", "fk_card_vault_tenant_id") is False
