"""Coverage tests for knowledge_expansion listed lines/arcs."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

from ai_knowledge.expansion.knowledge_expansion import KnowledgeExpander


def _make_expander(tmp_path, sources):
    def path_fn(name):
        return str(tmp_path / name)

    sources_file = tmp_path / "knowledge_sources.json"
    sources_file.write_text(json.dumps(sources), encoding="utf-8")
    with patch("ai_knowledge.get_knowledge_path", side_effect=path_fn):
        expander = KnowledgeExpander()
    return expander, path_fn


def _write_knowledge_file(tmp_path, filename, title, content):
    knowledge_dir = tmp_path / "expanded_knowledge"
    knowledge_dir.mkdir(exist_ok=True)
    payload = {"title": title, "content": content, "url": "https://example.com", "category": "general"}
    (knowledge_dir / filename).write_text(json.dumps(payload), encoding="utf-8")


def test_cov_ke_load_sources_returns_dict_line_40_41(tmp_path):
    """Lines 40-41: sources file holds a dict -> returned as-is."""
    payload = {"books": [], "websites": [], "documents": [], "last_updated": "x", "custom": 1}
    expander, _ = _make_expander(tmp_path, payload)
    assert expander.sources["custom"] == 1
    assert expander.sources["last_updated"] == "x"


def test_cov_ke_search_website_arcs(tmp_path):
    """Arcs 215->210 (no filename), 217->210 (missing file), 221->210 (no match)."""
    sources = {
        "websites": [
            {"category": "general", "url": "https://nofile.example"},
            {"category": "general", "filename": "gone.json", "url": "https://gone.example"},
            {"category": "general", "filename": "nomatch.json", "url": "https://a.example"},
            {"category": "general", "filename": "match.json", "url": "https://b.example"},
        ],
        "documents": [],
        "last_updated": None,
    }
    expander, _ = _make_expander(tmp_path, sources)
    _write_knowledge_file(tmp_path, "nomatch.json", "Unrelated title", "nothing relevant here")
    _write_knowledge_file(tmp_path, "match.json", "Target title", "this text mentions zirconium foobar")
    result = expander.search_knowledge("zirconium")
    assert result["success"] is True
    assert result["total_found"] == 1
    assert result["results"][0]["title"] == "Target title"


def test_cov_ke_search_document_arcs(tmp_path):
    """Arcs 241->236 (no filename), 243->236 (missing file), 247->236 (no match)."""
    sources = {
        "websites": [],
        "documents": [
            {"category": "general", "title": "NoFile"},
            {"category": "general", "filename": "gone_doc.json", "title": "Gone"},
            {"category": "general", "filename": "nomatch_doc.json", "title": "Plain"},
            {"category": "general", "filename": "match_doc.json", "title": "HitDoc"},
        ],
        "last_updated": None,
    }
    expander, _ = _make_expander(tmp_path, sources)
    knowledge_dir = tmp_path / "expanded_knowledge"
    knowledge_dir.mkdir(exist_ok=True)
    (knowledge_dir / "nomatch_doc.json").write_text(
        json.dumps({"title": "Plain", "content": "boring content", "category": "general"}),
        encoding="utf-8",
    )
    (knowledge_dir / "match_doc.json").write_text(
        json.dumps({"title": "HitDoc", "content": "contains quarkonium zebra", "category": "general"}),
        encoding="utf-8",
    )
    result = expander.search_knowledge("quarkonium")
    assert result["success"] is True
    assert result["total_found"] == 1
    assert result["results"][0]["title"] == "HitDoc"


def test_cov_ke_search_category_filter_skips(tmp_path):
    """Category mismatch continue paths for both website and document loops."""
    sources = {
        "websites": [{"category": "other", "filename": "m.json", "url": "https://m.example"}],
        "documents": [{"category": "other", "filename": "d.json", "title": "D"}],
        "last_updated": None,
    }
    expander, _ = _make_expander(tmp_path, sources)
    result = expander.search_knowledge("anything", category="general")
    assert result["success"] is True
    assert result["total_found"] == 0


def test_cov_ke_update_out_of_range_arc_339_347(tmp_path):
    """Arc 339->347: website index out of range returns source-type error."""
    sources = {
        "websites": [{"url": "https://example.com", "category": "general", "description": ""}],
        "documents": [],
        "last_updated": None,
    }
    expander, _ = _make_expander(tmp_path, sources)
    result = expander.update_knowledge_from_source("website", 99)
    assert result["success"] is False
    assert "نوع المصدر" in result["error"]


def test_cov_ke_update_invalid_type_arc_339_347(tmp_path):
    """Arc 339->347 complement: unsupported source type."""
    expander, _ = _make_expander(tmp_path, {"websites": [], "documents": [], "last_updated": None})
    result = expander.update_knowledge_from_source("book", 0)
    assert result["success"] is False


def test_cov_ke_update_valid_website_delegates(tmp_path):
    """True side of 339: valid website delegates to add_website."""
    sources = {
        "websites": [{"url": "https://example.com/x", "category": "general", "description": "d"}],
        "documents": [],
        "last_updated": None,
    }
    expander, _ = _make_expander(tmp_path, sources)
    with patch.object(KnowledgeExpander, "add_website", return_value={"success": True, "filename": "f"}) as mock_add:
        result = expander.update_knowledge_from_source("website", 0)
    assert result == {"success": True, "filename": "f"}
    mock_add.assert_called_once_with("https://example.com/x", "general", "d")


def test_cov_ke_save_sources_error_path(tmp_path, capsys):
    """Covers _save_sources except branch via read-only target is monkeypatched."""
    expander, _ = _make_expander(tmp_path, {"websites": [], "documents": [], "last_updated": None})
    with patch("builtins.open", side_effect=OSError("denied")):
        expander._save_sources()
    assert os.path.isdir(tmp_path / "expanded_knowledge")
    capsys.readouterr()
