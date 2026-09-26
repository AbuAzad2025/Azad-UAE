"""Per-route SQL query counter.

N+1 elimination cannot be reasoned about, it has to be measured. This module
counts SELECT statements per HTTP request and aggregates them per endpoint, so a
route that fans out into hundreds of queries is visible as a number instead of a
hunch.

Design constraints:

* zero cost when disabled — the listener returns on a module flag before doing any
  work, and the engine hook is only attached when profiling is switched on;
* reads only — INSERT/UPDATE/DELETE are counted separately so write-heavy
  endpoints are not mistaken for read N+1;
* aggregation happens in ``after_request`` so the number is per route lifecycle,
  not per test, and a redirect or an aborted request is still recorded.

Usage:

    from utils.query_profiler import enable_profiling, snapshot

    enable_profiling(app)
    ...
    snapshot()   # {endpoint: {"requests": n, "queries": m, "avg": m/n}}

Enable through the ``QUERY_PROFILE=1`` environment variable in CI or locally; it
is never enabled in production configuration.
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine

_ENABLED = False
_ATTACHED: set[int] = set()

# endpoint -> [requests, select_queries, write_queries]
_COUNTS: dict[str, list[int]] = {}

# set per request by the after_request hook
_LAST_SQL: dict[str, int] = {"select": 0, "write": 0}


def _flag_from_env() -> bool:
    return os.environ.get("QUERY_PROFILE", "").strip().lower() in {"1", "true", "yes", "on"}


def is_enabled() -> bool:
    return _ENABLED


def enable_profiling(app: Any = None) -> None:
    """Turn counting on and attach the engine listener (idempotent)."""
    global _ENABLED
    _ENABLED = True
    if app is not None:
        _attach_after_request(app)
        _flush_on_teardown(app)
    _attach_engine_listener()


def disable_profiling() -> None:
    global _ENABLED
    _ENABLED = False


def reset() -> None:
    _COUNTS.clear()


def snapshot() -> dict[str, dict[str, float]]:
    """endpoint -> requests / select_queries / write_queries / avg_selects."""
    out: dict[str, dict[str, float]] = {}
    for endpoint, (requests, selects, writes) in _COUNTS.items():
        out[endpoint] = {
            "requests": requests,
            "select_queries": selects,
            "write_queries": writes,
            "avg_selects": round(selects / requests, 2) if requests else 0.0,
            "max_selects_in_one_request": selects,
        }
    return out


def top(n: int = 20, by: str = "select_queries") -> list[tuple[str, dict[str, float]]]:
    data = snapshot()
    return sorted(data.items(), key=lambda kv: kv[1][by], reverse=True)[:n]


def report(n: int = 20) -> str:
    rows = top(n)
    lines = [f"{'endpoint':52s} {'reqs':>6s} {'selects':>9s} {'avg':>8s}"]
    lines.append("-" * 78)
    for endpoint, m in rows:
        lines.append(f"{endpoint:52s} {m['requests']:6.0f} {m['select_queries']:9.0f} {m['avg_selects']:8.2f}")
    return "\n".join(lines)


# ── internals ────────────────────────────────────────────────────────────────


def _bump_request(kind: str) -> None:
    if _ENABLED:
        _LAST_SQL[kind] += 1


def _current_endpoint() -> str:
    from flask import has_request_context, request

    if has_request_context():
        return request.endpoint or request.path
    return "<no-request>"


def _record_current_request() -> None:
    if not _ENABLED:
        return
    endpoint = _current_endpoint()
    rec = _COUNTS.setdefault(endpoint, [0, 0, 0])
    rec[0] += 1
    rec[1] += _LAST_SQL["select"]
    rec[2] += _LAST_SQL["write"]
    _LAST_SQL["select"] = 0
    _LAST_SQL["write"] = 0


@event.listens_for(Engine, "before_cursor_execute", named=True)
def _count_statement(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001, ARG001
    if not _ENABLED:
        return
    head = statement.lstrip()[:6].upper()
    if head.startswith("SELECT") or head.startswith("WITH"):
        _bump_request("select")
    elif head.startswith(("INSERT", "UPDATE", "DELETE")):
        _bump_request("write")


def _attach_engine_listener() -> None:
    # The decorator above registers on the Engine class at import time; nothing
    # per-engine is required, so _ATTACHED only guards the optional per-app hooks.
    _ATTACHED.add(id(Engine))


def _attach_after_request(app: Any) -> None:
    if getattr(app, "_query_profiler_hooked", False):
        return
    app.after_request(_record_current_request)
    app._query_profiler_hooked = True


def _flush_on_teardown(app: Any) -> None:
    """Record requests that never reach after_request (aborted / 4xx early exit)."""
    if getattr(app, "_query_profiler_teardown_hooked", False):
        return

    from flask import g, has_request_context

    @app.teardown_request
    def _teardown(exc):  # noqa: ANN001, ARG001
        if not _ENABLED or not has_request_context():
            return
        if getattr(g, "_query_profiler_recorded", False):
            return
        g._query_profiler_recorded = True
        if _LAST_SQL["select"] or _LAST_SQL["write"]:
            _record_current_request()

    app._query_profiler_teardown_hooked = True
