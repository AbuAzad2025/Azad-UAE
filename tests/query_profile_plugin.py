"""Pytest plugin: profile SELECT counts per endpoint while the suite runs.

Enabled with QUERY_PROFILE=1. At the end of the session it writes the top-N
query-heavy routes so an N+1 refactor can be judged on a number.

    QUERY_PROFILE=1 python -m pytest tests/integration -p query_profile_plugin
"""

from __future__ import annotations

import os

import pytest

_ENABLED = os.environ.get("QUERY_PROFILE", "").strip().lower() in {"1", "true", "yes", "on"}
_TOP = int(os.environ.get("QUERY_PROFILE_TOP", "20"))


@pytest.hookimpl(trylast=True)
def pytest_sessionstart(session):  # noqa: ANN001, ARG001
    if not _ENABLED:
        return
    from utils.query_profiler import enable_profiling

    enable_profiling()
    session.config._query_profiling = True  # type: ignore[attr-defined]


def pytest_configure(config):  # noqa: ANN001
    if _ENABLED:
        config.add_cleanup(_emit)


def _emit() -> None:
    from utils.query_profiler import report, snapshot

    data = snapshot()
    out_dir = os.environ.get("QUERY_PROFILE_OUT", "")
    payload = report(_TOP)
    print("\n" + "=" * 78)
    print(f"QUERY PROFILE — top {_TOP} endpoints by total SELECT statements")
    print("=" * 78)
    print(payload)
    worst = sorted(data.items(), key=lambda kv: kv[1]["avg_selects"], reverse=True)[:10]
    print()
    print("top 10 by average SELECTs per request (the N+1 signal):")
    for endpoint, m in worst:
        print(f"  {endpoint:50s} avg={m['avg_selects']:8.2f} reqs={m['requests']:.0f}")
    if out_dir:
        import json

        with open(os.path.join(out_dir, "query_profile.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
        print(f"\nwritten -> {out_dir}/query_profile.json")
