"""The Alembic graph gate must catch copy-paste revision mistakes."""

from __future__ import annotations

import importlib.util
from pathlib import Path

GATE = Path(__file__).resolve().parents[3] / "scripts" / "lint" / "check_migration_head.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("check_migration_head_gate", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(tmp_path: Path, filename: str, revision: str, parent: str = "None") -> None:
    (tmp_path / filename).write_text(
        f'revision = "{revision}"\ndown_revision = {parent}\n\ndef upgrade():\n    pass\n\ndef downgrade():\n    pass\n',
        encoding="utf-8",
    )


def test_valid_chain_passes(tmp_path, monkeypatch, capsys):
    _write(tmp_path, "root_001_baseline.py", "root_001")
    _write(tmp_path, "a1b2c3_next.py", "a1b2c3", '"root_001"')
    gate = _load_gate()
    monkeypatch.setattr(gate, "VERSIONS", tmp_path)
    assert gate.main() == 0
    assert "OK:" in capsys.readouterr().out


def test_revision_id_not_matching_filename_fails(tmp_path, monkeypatch, capsys):
    _write(tmp_path, "a1b2c3_next.py", "WRONG_ID")
    gate = _load_gate()
    monkeypatch.setattr(gate, "VERSIONS", tmp_path)
    assert gate.main() == 1
    out = capsys.readouterr().out
    assert "revision id does not match filename" in out
    assert "a1b2c3_next.py declares revision=WRONG_ID" in out


def test_duplicate_revision_ids_fail(tmp_path, monkeypatch, capsys):
    _write(tmp_path, "root_001_baseline.py", "root_001")
    _write(tmp_path, "root_001_copy.py", "root_001", '"root_001"')
    gate = _load_gate()
    monkeypatch.setattr(gate, "VERSIONS", tmp_path)
    assert gate.main() == 1
    assert "duplicate revision id" in capsys.readouterr().out
