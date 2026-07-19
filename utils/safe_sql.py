"""
safe_sql — parameterized, identifier-validated SQL builders.

This module is the single, audited place where queries need a *dynamic table or
column name* (which can never be a bind parameter).  Instead of building raw
``text()`` strings with f-strings, every builder here:

1. Validates the requested table/column name against a strict SQL identifier
   grammar (``^[A-Za-z_][A-Za-z0-9_]*$``) and raises ``ValueError`` if it is not
   a safe identifier — so an attacker cannot inject an arbitrary identifier
   (``;``, quotes, whitespace, …).  Column/table existence is then enforced by
   the database engine itself when the statement is executed.
2. Constructs the statement with SQLAlchemy **core expressions**
   (``table()`` / ``column()`` / ``select()`` / ``delete()`` / ``update()`` /
   ``insert()``), which emit fully parameterized SQL.  No ``text()`` string
   interpolation is ever used for identifiers, eliminating B608 at the root.

Values are always embedded by SQLAlchemy as properly escaped bound literals —
never concatenated.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from sqlalchemy import (
    column as sa_column,
    delete,
    func,
    insert,
    inspect,
    select,
    table as sa_table,
    text as sa_text,
    update,
)
from sqlalchemy.schema import Column

__all__ = [
    "assert_known_table",
    "assert_known_column",
    "count_query",
    "select_all_query",
    "select_where_query",
    "select_in_query",
    "delete_where_query",
    "delete_all_query",
    "update_row_query",
    "insert_query",
    "nextval_query",
    "sa_table",
]

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def assert_known_table(bind: Any, name: str) -> str:
    """Raise ``ValueError`` unless ``name`` is a safe SQL identifier.

    Identifiers can never be passed as bind parameters, so we restrict them to
    the strict identifier grammar.  This blocks any injection characters
    (``;``, quotes, spaces, …).  The database engine enforces that the table
    actually exists when the statement is executed.
    """
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise ValueError(f"invalid table identifier: {name!r}")
    return name


def assert_known_column(bind: Any, table_name: str, column_name: str) -> str:
    """Raise ``ValueError`` unless ``column_name`` is a safe SQL identifier.

    See :func:`assert_known_table` — identifiers are validated against the
    strict grammar (no injection characters); the database enforces that the
    column actually exists when the statement is executed.
    """
    assert_known_table(bind, table_name)
    if not isinstance(column_name, str) or not _IDENT_RE.match(column_name):
        raise ValueError(f"invalid column identifier: {column_name!r}")
    return column_name


def _table(bind: Any, name: str, columns: Sequence[str] = ()):
    """Build a ``table()`` construct with the given (validated) columns.

    No database introspection is performed, so this works uniformly against
    real engines and mocked test connections.  The columns are declared so
    that core ``insert``/``update``/``where`` can reference them.
    """
    assert_known_table(bind, name)
    cols: List[Column] = [Column(c) for c in columns if _IDENT_RE.match(c)]
    return sa_table(name, *cols)


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
    stmt = select(sa_text("*")).select_from(tbl)
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
    """``SELECT * FROM <validated table> WHERE <validated col> = :value``.

    The value is embedded as a bound literal by SQLAlchemy (properly escaped),
    so no external bind parameters are required by the caller.
    """
    tbl = _table(bind, table_name, [column_name])
    assert_known_column(bind, table_name, column_name)
    stmt: Any = select(sa_text("*")).select_from(tbl).where(tbl.c[column_name] == value)
    if limit is not None:
        stmt = stmt.limit(limit)
    return stmt


def select_in_query(
    bind: Any,
    table_name: str,
    column_name: str,
    values: Sequence[Any],
):
    """``SELECT * FROM <validated table> WHERE <validated col> IN (...)``."""
    tbl = _table(bind, table_name, [column_name])
    assert_known_column(bind, table_name, column_name)
    if not values:
        return select(sa_text("*")).select_from(tbl).where(sa_column("__never__") == 1)
    stmt: Any = (
        select(sa_text("*")).select_from(tbl).where(tbl.c[column_name].in_(values))
    )
    return stmt


# ── Write builders ──────────────────────────────────────────────────────────


def delete_where_query(bind: Any, table_name: str, column_name: str, value: Any):
    """``DELETE FROM <validated table> WHERE <validated col> = :value``."""
    tbl = _table(bind, table_name, [column_name])
    assert_known_column(bind, table_name, column_name)
    return delete(tbl).where(tbl.c[column_name] == value)


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

    Only validated columns are accepted; values are embedded as bound literals.
    """
    assert_known_column(bind, table_name, pk_column)
    safe_updates: Dict[str, Any] = {}
    for col, val in updates.items():
        assert_known_column(bind, table_name, col)
        safe_updates[col] = val if val != "" else None
    tbl = _table(bind, table_name, [pk_column, *safe_updates.keys()])
    return update(tbl).where(tbl.c[pk_column] == row_id).values(**safe_updates)


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
    primary key, resolved via schema introspection when available).
    """
    from sqlalchemy.dialects import postgresql

    tbl = _table(bind, table_name, list(payload.keys()))
    if not payload:
        raise ValueError("empty insert payload")
    for col in payload:
        assert_known_column(bind, table_name, col)
    if on_conflict_do_nothing:
        try:
            pk = (
                inspect(bind).get_pk_constraint(table_name).get("constrained_columns")
                or []
            )
        except Exception:
            pk = []
        return (
            postgresql.insert(tbl)
            .values(dict(payload))
            .on_conflict_do_nothing(index_elements=pk)
        )
    return insert(tbl).values(dict(payload))


def nextval_query(bind: Any, sequence_name: str):
    """``SELECT nextval('<validated sequence>')`` via the core ``func`` construct.

    The sequence name is validated to be a plain identifier (no injection
    characters) and emitted through SQLAlchemy's ``func.nextval`` so no
    ``text()`` string interpolation is used.
    """
    sequence_name = str(sequence_name)
    if not sequence_name or not sequence_name.strip():
        raise ValueError("empty sequence name")
    if not all(ch.isalnum() or ch in "._-" for ch in sequence_name):
        raise ValueError(f"invalid sequence name: {sequence_name}")
    return select(func.nextval(sequence_name))
