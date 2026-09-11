"""Coverage-4 for services.backup_scoped_restore — remap/else arcs (real paths)."""

from __future__ import annotations

import json
import os
import tarfile

from services.backup_scoped_restore import (
    _apply_row_remap,
    _build_id_remap,
    _required_confirmation,
    extract_scoped_bundle,
)


class TestConfirmation:
    def test_values(self):
        assert _required_confirmation(False) == "RESTORE CONFIRM"
        assert _required_confirmation(True) == "REMAP CONFIRM"


class TestBuildIdRemap:
    def test_empty_tables(self):
        assert _build_id_remap({}, new_tenant_id=5) == {}

    def test_tenant_branch_store_roots(self):
        tables = {
            "tenants": [{"id": 1}],
            "branches": [{"id": 2}],
            "tenant_stores": [{"id": 3}],
            "sales": [{"id": 10}, {"id": 11}, {"no-id": True}],
        }
        maps = _build_id_remap(tables, new_tenant_id=9, new_branch_id=8, new_store_id=7)
        assert maps["tenants"] == {1: 9}
        assert maps["branches"] == {2: 8}
        assert maps["tenant_stores"] == {3: 7}
        # synthetic ids above max
        assert maps["sales"][10] >= 100000

    def test_branch_without_remap_gets_synthetic(self):
        tables = {"branches": [{"id": 2}], "tenants": [{"id": 1}]}
        maps = _build_id_remap(tables, new_tenant_id=9)
        assert maps["branches"][2] >= 100000


class TestApplyRowRemap:
    def test_tenant_rewrite_and_fk(self):
        id_maps = {"customers": {4: 40}}
        row = {"id": 1, "tenant_id": 2, "customer_id": 4, "branch_id": 3}
        out = _apply_row_remap(
            row, "sales", id_maps, new_tenant_id=9, old_tenant_id=2,
            scope="tenant", remap=False,
        )
        assert out["tenant_id"] == 9
        assert out["customer_id"] == 40

    def test_no_old_tenant_skips_rewrite(self):
        out = _apply_row_remap(
            {"tenant_id": 2}, "sales", {}, new_tenant_id=9, old_tenant_id=None, scope="tenant"
        )
        assert out["tenant_id"] == 2

    def test_branch_scope_forces_branch(self):
        out = _apply_row_remap(
            {"branch_id": 3}, "sales", {}, new_tenant_id=9, old_tenant_id=9,
            scope="branch", new_branch_id=77,
        )
        assert out["branch_id"] == 77

    def test_remap_slug_suffixes(self):
        out = _apply_row_remap(
            {"slug": "acme"}, "tenants", {}, new_tenant_id=9, old_tenant_id=1,
            scope="tenant", remap=True,
        )
        assert out["slug"] == "acme_r9"
        out2 = _apply_row_remap(
            {"store_slug": "shop"}, "tenant_stores", {}, new_tenant_id=9, old_tenant_id=1,
            scope="store", remap=True, new_store_id=5,
        )
        assert out2["store_slug"] == "shop_r5"

    def test_none_fk_skipped(self):
        out = _apply_row_remap(
            {"customer_id": None}, "sales", {}, new_tenant_id=9, old_tenant_id=9, scope="tenant"
        )
        assert out["customer_id"] is None


class TestExtractBundle:
    def _make_bundle(self, tmp_path, names_payload):
        arc = str(tmp_path / "b.tar.gz")
        src = tmp_path / "src"
        src.mkdir()
        (src / "manifest.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
        for name, payload in names_payload.items():
            p = src / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(payload, encoding="utf-8")
        with tarfile.open(arc, "w:gz") as tar:
            for name in ["manifest.json", *names_payload]:
                tar.add(str(src / name), arcname=name)
        return arc

    def test_missing_manifest_raises(self, tmp_path):
        arc = str(tmp_path / "bad.tar.gz")
        src = tmp_path / "s2"
        src.mkdir()
        (src / "other.txt").write_text("x", encoding="utf-8")
        with tarfile.open(arc, "w:gz") as tar:
            tar.add(str(src / "other.txt"), arcname="other.txt")
        work = str(tmp_path / "w")
        os.makedirs(work)
        import pytest

        with pytest.raises(RuntimeError, match="manifest"):
            extract_scoped_bundle(arc, work)

    def test_extract_with_data_dir(self, tmp_path):
        arc = self._make_bundle(tmp_path, {"data/sales.jsonl": '{"id": 1}\n'})
        work = str(tmp_path / "w1")
        os.makedirs(work)
        out = extract_scoped_bundle(arc, work)
        assert out["manifest"] == {"ok": True}
        assert "sales" in out["tables"]

    def test_extract_legacy_export(self, tmp_path):
        arc = self._make_bundle(tmp_path, {"tenant_export.json": json.dumps({"tables": {"sales": []}})})
        work = str(tmp_path / "w2")
        os.makedirs(work)
        out = extract_scoped_bundle(arc, work)
        assert out["tables"] == {"sales": []}
