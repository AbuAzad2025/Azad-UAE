"""Gap coverage: DepreciationService.run_monthly aggregation and error paths."""

from __future__ import annotations

from datetime import date

import services.depreciation_service as dep_mod
from models.fixed_asset import FixedAsset


class _FakeQuery:
    def __init__(self, assets, filters):
        self._assets = assets
        self._filters = filters

    def filter_by(self, **kw):
        assert kw == {"status": "active"}
        return self

    def filter(self, *criteria):
        self._filters.extend(criteria)
        return self

    def all(self):
        return self._assets


class _Asset:
    def __init__(self, number, behavior):
        self.asset_number = number
        self._behavior = behavior

    def post_depreciation(self, period_date=None):
        return self._behavior(period_date)


def _install(monkeypatch, assets):
    filters = []
    monkeypatch.setattr(FixedAsset, "query", _FakeQuery(assets, filters), raising=False)
    return filters


def test_counts_posted_and_skipped(monkeypatch):
    seen_dates = []

    def record(period_date):
        seen_dates.append(period_date)
        return {"amount": 1}

    assets = [
        _Asset("FA-1", lambda pd: None),
        _Asset("FA-2", record),
        _Asset("FA-3", lambda pd: {"amount": 2}),
    ]
    _install(monkeypatch, assets)
    result = dep_mod.DepreciationService.run_monthly(None, period_year=2026, period_month=3)
    assert result == {"posted": 2, "skipped": 1, "errors": []}
    assert seen_dates == [date(2026, 3, 1)]


def test_default_period_is_current_utc_month(monkeypatch):
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    captured = {}

    def cb(period_date):
        captured["pd"] = period_date
        return None

    _install(monkeypatch, [_Asset("FA-D", cb)])
    dep_mod.DepreciationService.run_monthly(None)
    assert captured["pd"] == date(now.year, now.month, 1)


def test_tenant_filter_converts_to_int(monkeypatch):
    filters = _install(monkeypatch, [])
    dep_mod.DepreciationService.run_monthly("42")
    assert len(filters) == 1
    expr = filters[0]
    assert int(expr.right.value) == 42


def test_no_tenant_skips_tenant_filter(monkeypatch):
    filters = _install(monkeypatch, [])
    dep_mod.DepreciationService.run_monthly(None)
    assert filters == []


def test_already_depreciated_valueerror_counts_as_skipped(monkeypatch):
    def already(pd):
        raise ValueError("الأصل مُهلك مسبقاً لهذه الفترة")

    _install(monkeypatch, [_Asset("FA-A", already)])
    out = dep_mod.DepreciationService.run_monthly(None, period_year=2025, period_month=1)
    assert out["skipped"] == 1
    assert out["posted"] == 0
    assert out["errors"] == []


def test_other_valueerror_recorded_in_errors(monkeypatch):
    def bad(pd):
        raise ValueError("salvage value exceeded cost")

    _install(monkeypatch, [_Asset("FA-BAD", bad)])
    out = dep_mod.DepreciationService.run_monthly(None)
    assert out["errors"] == ["FA-BAD: salvage value exceeded cost"]
    assert out["posted"] == 0


def test_unexpected_exception_recorded_and_run_continues(monkeypatch):
    assets = [
        _Asset("FA-X", lambda pd: (_ for _ in ()).throw(RuntimeError("boom"))),
        _Asset("FA-Y", lambda pd: ({"ok": True})),
    ]
    _install(monkeypatch, assets)
    out = dep_mod.DepreciationService.run_monthly(None)
    assert out["errors"] == ["FA-X: boom"]
    assert out["posted"] == 1


def test_empty_asset_set_returns_zero_summary(monkeypatch):
    _install(monkeypatch, [])
    out = dep_mod.DepreciationService.run_monthly("7")
    assert out == {"posted": 0, "skipped": 0, "errors": []}


def test_flush_inside_atomic_transaction_called_once(monkeypatch):
    calls = []
    real_atomic = dep_mod.atomic_transaction

    def spy(description="unnamed"):
        calls.append(description)
        return real_atomic(description)

    monkeypatch.setattr(dep_mod, "atomic_transaction", spy)
    flush_calls = []

    def flush_spy():
        flush_calls.append(True)
        return None

    monkeypatch.setattr(dep_mod.db.session, "flush", flush_spy)
    _install(monkeypatch, [])
    dep_mod.DepreciationService.run_monthly(None)
    assert calls == ["depreciation_run_monthly"]
    assert len(flush_calls) == 1
