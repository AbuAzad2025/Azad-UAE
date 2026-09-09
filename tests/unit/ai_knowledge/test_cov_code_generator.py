"""Coverage tests for code_generator listed lines/arcs."""

from __future__ import annotations

import pytest

from ai_knowledge.generation.code_generator import CodeGenerator, _ident


def test_cov_cg_ident_rejects_unsafe_line_29():
    """Line 29: unsafe identifier raises ValueError."""
    with pytest.raises(ValueError):
        _ident("bad-table!")
    with pytest.raises(ValueError):
        _ident("123abc")
    with pytest.raises(ValueError):
        _ident("")
    assert _ident("users") == "users"


def test_cov_cg_ident_rejected_in_select_returns_error():
    """Unsafe table name flows into the caught-Exception error string."""
    out = CodeGenerator.generate_sql_query("select", "bad-table!")
    assert out.startswith("-- Error")


def test_cov_cg_insert_without_values_line_129():
    """Line 129: insert with no columns/values takes the bare-insert branch."""
    out = CodeGenerator.generate_sql_query("insert", "users")
    assert "INSERT" in out.upper()
    out2 = CodeGenerator.generate_sql_query("insert", "users", {"columns": ["name"]})
    assert "INSERT" in out2.upper()


def test_cov_cg_insert_with_values_true_side():
    """Insert true side: columns+values renders a VALUES clause."""
    out = CodeGenerator.generate_sql_query("insert", "users", {"columns": ["name"], "values": ["ali"]})
    assert "INSERT" in out.upper()


def test_cov_cg_update_no_filters_arc_135_138():
    """Arc 135->138: update with filters=None skips set parsing."""
    out = CodeGenerator.generate_sql_query("update", "users")
    assert "UPDATE" in out.upper()


def test_cov_cg_update_where_only_arc_141_143():
    """Arc 141->143: update with where but no set skips .values()."""
    out = CodeGenerator.generate_sql_query("update", "users", {"where": {"id": 1}})
    assert "UPDATE" in out.upper()
    assert "WHERE" in out.upper()


def test_cov_cg_update_set_only_arc_144_146():
    """Arc 144->146: update with set but no where skips .where()."""
    out = CodeGenerator.generate_sql_query("update", "users", {"set": {"name": "ali"}})
    assert "UPDATE" in out.upper()
    assert "WHERE" not in out.upper()


def test_cov_cg_update_set_and_where_true_sides():
    """True sides of 141/144: set + where both applied."""
    out = CodeGenerator.generate_sql_query("update", "users", {"set": {"name": "ali"}, "where": {"id": 2}})
    assert "UPDATE" in out.upper()
    assert "WHERE" in out.upper()


def test_cov_cg_fix_nameerror_without_match_arc_332_340():
    """Arc 332->340: NameError text without the expected pattern."""
    result = CodeGenerator.fix_code("x = 1", "NameError: something else broke")
    assert result["changes"] == []
    assert result["confidence"] == 0.3


def test_cov_cg_fix_nameerror_unknown_name_arc_336_340():
    """Arc 336->340: matched name is not db/func so no import added."""
    result = CodeGenerator.fix_code("print(foobar)", "NameError: name 'foobar' is not defined")
    assert result["changes"] == []
    assert "foobar" not in result["fixed_code"] or "from extensions import" not in result["fixed_code"]


def test_cov_cg_fix_nameerror_db_true_side():
    """True sides of 332/336: missing db gets an import."""
    result = CodeGenerator.fix_code("db.session.add(x)", "NameError: name 'db' is not defined")
    assert any("db" in c for c in result["changes"])
    assert result["fixed_code"].startswith("from extensions import db")
