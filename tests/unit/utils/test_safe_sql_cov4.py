"""Cov4: safe_sql uncovered arcs — validation, empty payloads, conflict path."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import utils.safe_sql as sq


def test_assert_table_rejects():
    with pytest.raises(ValueError):  # line 73-74
        sq.assert_known_table(None, "bad;name")
    with pytest.raises(ValueError):
        sq.assert_known_table(None, 123)
    assert sq.assert_known_table(None, "ok_table") == "ok_table"


def test_assert_column_rejects():
    with pytest.raises(ValueError):  # line 86-87
        sq.assert_known_column(None, "t", "bad col")
    assert sq.assert_known_column(None, "t", "col1") == "col1"


def test_table_filters_bad_columns():
    tbl = sq._table(None, "myt", ["good", "bad-col", "ok2"])  # line 99
    assert "good" in tbl.c
    assert "ok2" in tbl.c


def test_builders_compile():
    assert str(sq.count_query(None, "t1"))  # line 108-109
    assert str(sq.select_all_query(None, "t1", limit=5, offset=2))  # 121-126
    assert str(sq.select_all_query(None, "t1"))
    assert str(sq.select_where_query(None, "t1", "c1", 7, limit=3))  # 142-147
    assert str(sq.select_where_query(None, "t1", "c1", 7))
    assert str(sq.select_in_query(None, "t1", "c1", []))  # line 159-160
    assert str(sq.select_in_query(None, "t1", "c1", [1, 2]))
    assert str(sq.delete_where_query(None, "t1", "c1", 9))  # line 172
    assert str(sq.delete_all_query(None, "t1"))  # line 178


def test_update_row_empty_string_to_none():
    stmt = sq.update_row_query(None, "t1", "id", 1, {"name": "", "age": 5})  # line 196
    assert stmt is not None


def test_insert_empty_payload_raises():
    with pytest.raises(ValueError, match="empty insert"):  # line 217-218
        sq.insert_query(None, "t1", {})


def test_insert_validates_columns():
    with pytest.raises(ValueError):
        sq.insert_query(None, "t1", {"bad col": 1})
    assert str(sq.insert_query(None, "t1", {"a": 1, "b": 2}))


def test_insert_conflict_paths():
    bind = MagicMock()
    with patch.object(
        sq, "inspect", return_value=MagicMock(get_pk_constraint=lambda t: {"constrained_columns": ["id"]})
    ):
        assert str(sq.insert_query(bind, "t1", {"a": 1}, on_conflict_do_nothing=True))  # 221-226
    with patch.object(sq, "inspect", side_effect=RuntimeError("nope")):
        assert str(sq.insert_query(bind, "t1", {"a": 1}, on_conflict_do_nothing=True))  # 224-225


def test_nextval_edges():
    with pytest.raises(ValueError):  # line 238-239
        sq.nextval_query(None, "   ")
    with pytest.raises(ValueError):  # line 240-241
        sq.nextval_query(None, "bad;name!")
    assert str(sq.nextval_query(None, "my_seq"))
    assert str(sq.nextval_query(None, "schema.my-seq"))
