"""Unit tests for the per-route query profiler.

The aggregation logic must be trustworthy before it is used to justify an N+1
refactor, so it is tested directly here: no database, no Flask request, just the
counters and the report it produces.
"""

from __future__ import annotations

import pytest

from utils import query_profiler as qp


@pytest.fixture(autouse=True)
def _clean():
    qp.reset()
    qp._LAST_SQL["select"] = 0
    qp._LAST_SQL["write"] = 0
    yield
    qp.reset()
    qp.disable_profiling()


def _count(statement: str) -> None:
    """Drive the listener the way SQLAlchemy would."""
    qp._count_statement(None, None, statement, None, None, False)


def test_disabled_profiler_counts_nothing():
    qp.disable_profiling()
    _count("SELECT 1")
    assert qp.snapshot() == {}


def test_select_statements_are_counted():
    qp.enable_profiling()
    _count("SELECT * FROM sales")
    _count("  select 1")
    _count("WITH x AS (SELECT 1) SELECT * FROM x")
    assert qp._LAST_SQL["select"] == 3
    assert qp._LAST_SQL["write"] == 0


def test_writes_are_counted_separately():
    qp.enable_profiling()
    _count("INSERT INTO sales VALUES (1)")
    _count("UPDATE sales SET x=1")
    _count("DELETE FROM sales")
    assert qp._LAST_SQL["write"] == 3
    assert qp._LAST_SQL["select"] == 0


def test_non_dml_is_ignored():
    qp.enable_profiling()
    _count("SET search_path TO public")
    _count("CREATE TABLE t (id int)")
    _count("COMMIT")
    assert qp._LAST_SQL["select"] == 0
    assert qp._LAST_SQL["write"] == 0


def test_snapshot_aggregates_requests_and_averages():
    qp.enable_profiling()
    for _ in range(2):
        qp._COUNTS.setdefault("sales.index", [0, 0, 0])
        rec = qp._COUNTS["sales.index"]
        rec[0] += 1
        rec[1] += 10
        rec[2] += 1
    qp._COUNTS.setdefault("reports.sales", [1, 100, 0])

    snap = qp.snapshot()
    assert snap["sales.index"]["requests"] == 2
    assert snap["sales.index"]["select_queries"] == 20
    assert snap["sales.index"]["avg_selects"] == 10.0
    assert snap["reports.sales"]["avg_selects"] == 100.0


def test_top_orders_by_total_then_average():
    qp._COUNTS["a.route"] = [1, 50, 0]
    qp._COUNTS["b.route"] = [100, 500, 0]
    qp._COUNTS["c.route"] = [1, 90, 0]

    by_total = [k for k, _ in qp.top(3, by="select_queries")]
    assert by_total[0] == "b.route"
    assert set(by_total) == {"a.route", "b.route", "c.route"}

    by_avg = [k for k, _ in qp.top(3, by="avg_selects")]
    assert by_avg[0] == "c.route"


def test_report_renders_every_column():
    qp._COUNTS["x.route"] = [3, 30, 2]
    text = qp.report(5)
    assert "x.route" in text
    assert "endpoint" in text
    assert "avg" in text


def test_endpoint_label_survives_ambient_request_context():
    """Regression: CI failed here because another test left a request context pushed.

    The helper is called from teardown_request and from the SQL listener, so it
    must behave correctly whether or not a request happens to be active. This
    pins both branches explicitly instead of relying on suite ordering.
    """
    from flask import Flask, request

    flask_app = Flask(__name__)

    with flask_app.test_request_context("/dashboard"):
        live = qp._current_endpoint()
        assert live == (request.endpoint or request.path)
        assert live != "<no-request>"

    # after the context pops, the fallback must return
    assert qp._current_endpoint() == "<no-request>"


def test_endpoint_label_prefers_live_request():
    """Inside a request context the label is the endpoint, not the fallback."""
    from flask import Flask, request

    flask_app = Flask(__name__)
    with flask_app.test_request_context("/dashboard"):
        assert qp._current_endpoint() == (request.endpoint or request.path)
