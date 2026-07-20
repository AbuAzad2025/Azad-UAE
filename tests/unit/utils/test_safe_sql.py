import pytest
from sqlalchemy import create_engine, insert, MetaData, Table, Column, Integer, String

from utils.safe_sql import (
    assert_known_column,
    assert_known_table,
    count_query,
    delete_all_query,
    delete_where_query,
    insert_query,
    nextval_query,
    select_all_query,
    select_in_query,
    select_where_query,
    update_row_query,
)


@pytest.fixture
def engine():
    eng = create_engine("sqlite://")
    meta = MetaData()
    Table(
        "widgets",
        meta,
        Column("id", Integer, primary_key=True),
        Column("name", String),
        Column("tenant_id", Integer),
    )
    meta.create_all(eng)
    with eng.begin() as conn:
        widgets = Table("widgets", MetaData(), autoload_with=eng)
        conn.execute(
            insert(widgets).values(
                [
                    {"id": 1, "name": "a", "tenant_id": 7},
                    {"id": 2, "name": "b", "tenant_id": 7},
                    {"id": 3, "name": "c", "tenant_id": 9},
                ]
            )
        )
    return eng


def test_assert_known_table_ok(engine):
    assert_known_table(engine, "widgets")


def test_assert_known_table_rejects_invalid_format(engine):
    for bad in ("", "evil; DROP", "a b", "1table", '"x"'):
        with pytest.raises(ValueError):
            assert_known_table(engine, bad)


def test_assert_known_column_ok(engine):
    assert_known_column(engine, "widgets", "tenant_id")


def test_assert_known_column_rejects_invalid_format(engine):
    for bad in ("", "evil; DROP", "a b", '"x"'):
        with pytest.raises(ValueError):
            assert_known_column(engine, "widgets", bad)


def test_count_query_parameterized(engine):
    with engine.connect() as conn:
        n = conn.execute(count_query(engine, "widgets")).scalar()
    assert n == 3


def test_select_where_query_binds_values(engine):
    with engine.connect() as conn:
        result = conn.execute(select_where_query(engine, "widgets", "tenant_id", 7))
        rows = [dict(zip(result.keys(), r)) for r in result.fetchall()]
    assert len(rows) == 2
    assert {r["name"] for r in rows} == {"a", "b"}


def test_select_in_query_binds_values(engine):
    with engine.connect() as conn:
        result = conn.execute(select_in_query(engine, "widgets", "id", [1, 3]))
        rows = [dict(zip(result.keys(), r)) for r in result.fetchall()]
    assert {r["tenant_id"] for r in rows} == {7, 9}


def test_select_all_query(engine):
    with engine.connect() as conn:
        result = conn.execute(select_all_query(engine, "widgets"))
        rows = [dict(zip(result.keys(), r)) for r in result.fetchall()]
    assert len(rows) == 3


def test_insert_query_parameterized(engine):
    with engine.begin() as conn:
        conn.execute(insert_query(engine, "widgets", {"id": 10, "name": "z", "tenant_id": 7}))
    with engine.connect() as conn:
        n = conn.execute(count_query(engine, "widgets")).scalar()
    assert n == 4


def test_update_row_query_parameterized(engine):
    with engine.begin() as conn:
        conn.execute(update_row_query(engine, "widgets", "id", 1, {"name": "renamed"}))
    with engine.connect() as conn:
        result = conn.execute(select_where_query(engine, "widgets", "id", 1))
        row = dict(zip(result.keys(), result.fetchone()))
    assert row["name"] == "renamed"


def test_delete_where_query_parameterized(engine):
    with engine.begin() as conn:
        conn.execute(delete_where_query(engine, "widgets", "tenant_id", 9))
    with engine.connect() as conn:
        n = conn.execute(count_query(engine, "widgets")).scalar()
    assert n == 2


def test_delete_all_query(engine):
    with engine.begin() as conn:
        conn.execute(delete_all_query(engine, "widgets"))
    with engine.connect() as conn:
        n = conn.execute(count_query(engine, "widgets")).scalar()
    assert n == 0


def test_nextval_query_rejects_invalid_name(engine):
    with pytest.raises(ValueError):
        nextval_query(engine, "widgets; DROP TABLE widgets")
    with pytest.raises(ValueError):
        nextval_query(engine, "")
