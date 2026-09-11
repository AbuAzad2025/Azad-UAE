"""Coverage-4 for services.backup_scoped_engine — pure/else arcs (real paths)."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from services.backup_scoped_engine import (
    ExportResult,
    _json_default,
    _new_id,
    _remap_row,
    export_scope,
    read_jsonl,
    write_checksums_file,
    write_data_bundle,
    write_jsonl,
)


class TestJsonDefault:
    def test_datetime_family(self):
        assert _json_default(datetime(2026, 1, 1)) == "2026-01-01T00:00:00"
        assert _json_default(date(2026, 1, 2)) == "2026-01-02"
        assert _json_default(time(3, 4)) == "03:04:00"

    def test_decimal_bytes_uuid_fallback(self):
        assert _json_default(Decimal("1.5")) == "1.5"
        assert _json_default(b"\x00ff") == b"\x00ff".hex()
        uid = uuid4()
        assert _json_default(uid) == str(uid)
        assert _json_default(object()) != ""


class TestJsonlRoundtrip:
    def test_missing_file_returns_empty(self, tmp_path):
        assert read_jsonl(str(tmp_path / "nope.jsonl")) == []

    def test_write_read_and_blank_lines(self, tmp_path):
        path = str(tmp_path / "a.jsonl")
        write_jsonl(path, [{"a": 1}, {"b": Decimal("2.5")}])
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n")
        rows = read_jsonl(path)
        assert rows[0] == {"a": 1}

    def test_checksums_skips_missing(self, tmp_path):
        (tmp_path / "keep.txt").write_text("hi", encoding="utf-8")
        out = write_checksums_file(str(tmp_path), ["keep.txt", "missing.txt"])
        assert os.path.isfile(out)
        assert "missing.txt" not in open(out, encoding="utf-8").read()


class TestRemapRow:
    def test_pk_and_tenant_and_fk(self):
        id_maps = {"tenants": {1: 9}, "branches": {2: 8}}
        out = _remap_row({"id": 5, "tenant_id": 1}, "tenants", {**id_maps, "tenants": {5: 50}}, force_tenant_id=9)
        assert out["id"] == 50
        assert out["tenant_id"] == 9

    def test_fk_none_skipped_and_unknown_table(self):
        out = _remap_row({"id": 1, "branch_id": None}, "sales", {}, force_tenant_id=None)
        assert out == {"id": 1, "branch_id": None}
        out2 = _remap_row({"id": 1}, "unknown_table", {"unknown_table": {1: 2}})
        assert out2["id"] == 2

    def test_fk_remapped_when_known(self):
        id_maps = {"branches": {3: 30}}
        out = _remap_row({"id": 1, "branch_id": 3}, "sales", id_maps)
        assert out["branch_id"] == 30


class TestNewId:
    def test_sequence_path(self):
        conn = MagicMock()
        conn.execute.return_value.scalar.side_effect = ["my_seq", 77]
        assert _new_id(conn, "sales") == 77

    def test_max_plus_one_path(self):
        conn = MagicMock()
        conn.execute.return_value.scalar.side_effect = [None, 41]
        assert _new_id(conn, "sales") == 41


class TestExportScopeOrdering:
    def test_extra_table_appended_after_order(self, mocker):
        import services.backup_scoped_engine as eng

        mocker.patch.object(
            eng,
            "export_scoped_database",
            return_value=({"sales": [{"id": 1}], "zzz_custom": [{"id": 2}]}, {"sales": 1}, ["sales"], [], []),
        )
        out = export_scope(MagicMock(), "tenant", tenant_id=1)
        assert isinstance(out, ExportResult)
        assert out.dependency_order.index("sales") < out.dependency_order.index("zzz_custom")


class TestWriteDataBundle:
    def test_skips_empty_and_writes_meta(self, tmp_path):
        conn = MagicMock()
        from unittest.mock import patch

        import services.backup_scoped_engine as eng

        exp = ExportResult(
            tables={"sales": [{"id": 1}], "empty_t": []},
            row_counts={},
            included=["sales"],
            skipped=[],
            dependency_order=["sales", "empty_t"],
            scope="tenant",
            tenant_id=1,
        )
        with patch.object(eng, "table_exists", return_value=False):
            meta = write_data_bundle(str(tmp_path), exp, conn)
        assert "schema_meta" in meta
        assert os.path.isfile(str(tmp_path / "sales.jsonl"))
        assert json.loads(open(str(tmp_path / "export_meta.json"), encoding="utf-8").read())["scope"] == "tenant"
