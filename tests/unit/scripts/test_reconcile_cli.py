"""The reconciliation CLI must persist corrections, not just report them."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from scripts.ops import reconcile_historical_balances as cli


def _run(monkeypatch, *args):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user@host/db")
    monkeypatch.setattr("sys.argv", ["reconcile_historical_balances.py", *args])

    report = {
        "customers": [{"id": 1, "before": "9.000", "after": "1.000"}],
        "suppliers": [],
        "partners": [],
        "applied": "--apply" in args,
        "total_discrepancies": 1,
    }
    session = MagicMock()
    session.execute.return_value.scalar.return_value = "testdb"
    session.connection.return_value = object()
    session_cm = MagicMock()
    session_cm.__enter__ = MagicMock(return_value=session)
    session_cm.__exit__ = MagicMock(return_value=False)

    with (
        patch.object(cli, "create_engine") as engine,
        patch.object(cli, "Session", return_value=session_cm),
        patch.object(cli, "reconcile", return_value=report) as reconcile,
    ):
        engine.return_value.dispose = MagicMock()
        code = cli.main()
    return code, session, reconcile


def test_apply_commits_the_corrections(monkeypatch, capsys):
    code, session, reconcile = _run(monkeypatch, "--apply")
    assert code == 0
    assert reconcile.call_args.kwargs["apply"] is True
    session.commit.assert_called_once_with()
    assert "testdb" in capsys.readouterr().out


def test_dry_run_never_commits(monkeypatch):
    code, session, reconcile = _run(monkeypatch)
    assert code == 1  # discrepancies found, nothing applied
    assert reconcile.call_args.kwargs["apply"] is False
    session.commit.assert_not_called()
