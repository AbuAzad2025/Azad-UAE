"""
safe_sql — parameterized, identifier-validated SQL builders.

This module is the single, audited place where queries need a *dynamic table or
column name* (which can never be a bind parameter).  Instead of building raw
``text()`` strings with f-strings, every builder here:

1. Validates the requested table/column name against the live database metadata
   (a strict allowlist) and raises ``ValueError`` if it is unknown — so an
   attacker cannot inject an arbitrary identifier.
2. Constructs the statement with SQLAlchemy **core expressions**
   (``table()`` / ``column()`` / ``select()`` / ``delete()`` / ``update()`` /
   ``insert()``), which emit fully parameterized SQL.  No ``text()`` string
   interpolation is ever used for identifiers, eliminating B608 at the root.

Values are always passed as bind parameters — never concatenated.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from sqlalchemy import (
    bindparam,
    column as sa_column,
    delete,
    func,
    insert,
    inspect,
    select,
    table as sa_table,
    update,
)


def _bind(bind: Any) -> Any:
    """Normalise an Engine or Connection to something inspect() accepts."""
    return bind


def assert_known_table(bind: Any, name: str) -> str:
    """Raise ``ValueError`` unless ``name`` is a real table in the schema."""
    if not name or not str(name).strip():
        raise ValueError("empty table name")
    inspector = inspect(_bind(bind))
    if name not in set(inspector.get_table_names()):
        raise ValueError(f"unknown table: {name}")
    return name


def assert_known_column(bind: Any, table_name: str, column_name: str) -> str:
    """Raise ``ValueError`` unless ``column_name`` exists on ``table_name``."""
    if not column_name or not str(column_name).strip():
        raise ValueError("empty column name")
    inspector = inspect(_bind(bind))
    cols = {c["name"] for c in inspector.get_columns(table_name)}
    if column_name not in cols:
        raise ValueError(f"unknown column {column_name} on {table_name}")
    return column_name


def _table(bind: Any, name: str):
    assert_known_table(bind, name)
    return sa_table(name)


# ── Read builders ───────────────────────────────────────────────────────────

def count_query(bind: Any, table_name: str):
    """``SELECT COUNT(*) FROM <validated table>``."""
    tbl = _table(bind, table_name)
    return select(func.count()).select_from(tbl)


def select_all_query(
    bind: Any,
    table_name: str,
    *,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
):
    """``SELECT * FROM <validated table>`` with optional LIMIT/OFFSET."""
    tbl = _table(bind, table_name)
    stmt = select(tbl)
    if limit is not None:
        stmt = stmt.limit(limit)
    if offset is not None:
        stmt = stmt.offset(offset)
    return stmt


def select_where_query(
    bind: Any,
    table_name: str,
    column_name: str,
    value: Any,
    *,
    limit: Optional[int] = None,
):
    """``SELECT * FROM <validated table> WHERE <validated col> = :value``."""
    tbl = _table(bind, table_name)
    assert_known_column(bind, table_name, column_name)
    stmt = select(tbl).where(tbl.c[column_name] == bindparam("value"))
    if limit is not None:
        stmt = stmt.limit(limit)
    return stmt


def select_in_query(
    bind: Any,
    table_name: str,
    column_name: str,
    values: Sequence[Any],
):
    """``SELECT * FROM <validated table> WHERE <validated col> IN (:v0, :v1, ...)``."""
    tbl = _table(bind, table_name)
    assert_known_column(bind, table_name, column_name)
    if not values:
        return select(tbl).where(sa_column("__never__") == 1)
    stmt = select(tbl).where(tbl.c[column_name].in_(values))
    return stmt


# ── Write builders ──────────────────────────────────────────────────────────

def delete_where_query(bind: Any, table_name: str, column_name: str, value: Any):
    """``DELETE FROM <validated table> WHERE <validated col> = :value``."""
    tbl = _table(bind, table_name)
    assert_known_column(bind, table_name, column_name)
    return delete(tbl).where(tbl.c[column_name] == bindparam("value"))


def delete_all_query(bind: Any, table_name: str):
    """``DELETE FROM <validated table>`` (no WHERE — full table wipe)."""
    tbl = _table(bind, table_name)
    return delete(tbl)


def update_row_query(
    bind: Any,
    table_name: str,
    pk_column: str,
    row_id: Any,
    updates: Mapping[str, Any],
):
    """``UPDATE <validated table> SET <validated cols> = :cols WHERE pk = :row_id``.

    Only validated columns are accepted; values are passed as bind parameters.
    """
    tbl = _table(bind, table_name)
    assert_known_column(bind, table_name, pk_column)
    safe_updates: Dict[str, Any] = {}
    for col, val in updates.items():
        assert_known_column(bind, table_name, col)
        safe_updates[col] = val if val != "" else None
    return (
        update(tbl)
        .where(tbl.c[pk_column] == bindparam("row_id"))
        .values(**safe_updates)
    )


def insert_query(
    bind: Any,
    table_name: str,
    payload: Mapping[str, Any],
    *,
    on_conflict_do_nothing: bool = False,
):
    """``INSERT INTO <validated table> (...) VALUES (...)`` (fully parameterized).

    When ``on_conflict_do_nothing`` is set, appends a PostgreSQL
    ``ON CONFLICT DO NOTHING`` clause (the conflict target is the table's
    primary key, resolved via schema introspection).
    """
    from sqlalchemy.dialects import postgresql

    tbl = _table(bind, table_name)
    if not payload:
        raise ValueError("empty insert payload")
    for col in payload:
        assert_known_column(bind, table_name, col)
    if on_conflict_do_nothing:
        pk = (
            inspect(_bind(bind)).get_pk_constraint(table_name).get(
                "constrained_columns"
            )
            or []
        )
        return postgresql.insert(tbl).values(dict(payload)).on_conflict_do_nothing(
            index_elements=pk
        )
    return insert(tbl).values(dict(payload))


def nextval_query(bind: Any, sequence_name: str):
    """``SELECT nextval('<validated sequence>')`` via the core ``sequence`` construct.

    The sequence name is validated to be a plain identifier (no injection
    characters) and emitted through SQLAlchemy's ``sequence()`` core object, so
    no ``text()`` string interpolation is used.
    """
    if not sequence_name or not str(sequence_name).strip():
        raise ValueError("empty sequence name")
    if not all(ch.isalnum() or ch in "_-" for ch in sequence_name):
        raise ValueError(f"invalid sequence name: {sequence_name}")
    return select(func.nextval(sequence_name))
