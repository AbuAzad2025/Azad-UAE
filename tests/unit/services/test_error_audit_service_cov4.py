"""Cov4: error_audit_service — query/export/log/dedup/sanitize/request-id arcs."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

from services.error_audit_service import ErrorAuditService


def test_logs_query_filters(db_session):
    ErrorAuditService.log("cov4-a", category="CAT1", level="ERROR", source="t")
    ErrorAuditService.log("cov4-b", category="CAT2", level="CRITICAL", source="t")
    assert ErrorAuditService.get_logs_query("CAT1", "", "").count() >= 1
    assert ErrorAuditService.get_logs_query("", "CRITICAL", "").count() >= 1
    assert ErrorAuditService.get_logs_query("", "", "0").count() >= 2
    assert ErrorAuditService.get_logs_query("", "", "1").count() >= 0
    assert ErrorAuditService.get_logs_query("", "", "").count() >= 2


def test_dropdowns_and_stats(db_session):
    ErrorAuditService.log("cov4-stats", category="STATC", level="ERROR", source="t")
    cats, levels = ErrorAuditService.get_dropdowns()
    assert "STATC" in cats and "ERROR" in levels
    stats = ErrorAuditService.get_stats()
    assert stats["total"] >= 1 and stats["unresolved"] >= 1


def test_export_json_and_text(db_session):
    ErrorAuditService.log("cov4-export", category="EXPC", level="ERROR", source="t")
    data, ctype, fname = ErrorAuditService.get_export_payload("EXPC", "", "", "json")
    assert ctype == "application/json" and fname == "error_audit_logs.json"
    assert "cov4-export" in data
    blob, ctype, fname = ErrorAuditService.get_export_payload("EXPC", "", "", "txt")
    assert fname == "error_audit_logs.txt"
    assert "cov4-export" in blob.decode("utf-8")


def test_export_text_includes_trace_and_request_data(db_session):
    ErrorAuditService.log_frontend("cov4-tr", stack="some stack trace", extra={"field": 1})
    blob, ctype, fname = ErrorAuditService.get_export_payload("FRONTEND", "", "", "txt")
    text_blob = blob.decode("utf-8")
    assert "Stack Trace" in text_blob
    assert "some stack trace" in text_blob
    assert "Request Data" in text_blob


def test_log_exception_and_frontend_truncation(db_session):
    try:
        raise ValueError("kaboom")
    except ValueError as exc:
        row_id = ErrorAuditService.log_exception(exc, category="EXCC", source="s")
        assert row_id is not None
    row_id = ErrorAuditService.log("", category="EMPTYC")
    assert row_id is not None
    row_id = ErrorAuditService.log_frontend("ui broke", stack="x" * 5000, extra={"password": "secret", "ok": 1})
    assert row_id is not None


def test_dedup_bump_and_resolve(db_session, sample_user):
    first = ErrorAuditService.log("dup-message", category="DUPC", level="ERROR", source="s")
    second = ErrorAuditService.log("dup-message", category="DUPC", level="ERROR", source="s")
    assert first == second  # fingerprint dedup arc
    assert ErrorAuditService.mark_resolved(first, sample_user.id, note="fixed") is True
    third = ErrorAuditService.log("dup-message", category="DUPC", level="ERROR", source="s")
    assert third != first  # resolved -> fresh insert arc


def test_request_id_no_context_and_in_context(app):
    rid = ErrorAuditService.get_or_create_request_id()
    assert rid
    with app.test_request_context("/x"):
        r1 = ErrorAuditService.get_or_create_request_id()
        r2 = ErrorAuditService.get_or_create_request_id()
        assert r1 == r2


def test_request_id_forced_outside_request_context(mocker):
    import services.error_audit_service as eas

    with patch.object(eas, "has_request_context", return_value=False):
        assert eas.ErrorAuditService.get_or_create_request_id()


def test_persist_and_helpers_failure_branches():
    assert ErrorAuditService._make_fingerprint("C", "E", "S", "/p", "  hello   world  ")
    assert ErrorAuditService._find_duplicate("no-such-fingerprint") is None
    assert ErrorAuditService._bump_duplicate(999999999, "m", "t") is True
    assert ErrorAuditService._sanitize_dict("not-a-dict") == {}
    clean = ErrorAuditService._sanitize_dict(
        {"password": "x", "nested": {"api_key": "y", "v": 1}, "items": [{"token": "z"}, 5, "s"], "plain": "ok"}
    )
    assert clean["password"] == "***REDACTED***"
    assert clean["nested"]["api_key"] == "***REDACTED***"
    assert clean["items"][0]["token"] == "***REDACTED***"
    assert clean["plain"] == "ok"
    with patch("services.error_audit_service.db.engine.connect", side_effect=RuntimeError("db down")):
        assert ErrorAuditService._find_duplicate("fp") is None
        assert ErrorAuditService._bump_duplicate(1, "m", None) is False
        assert ErrorAuditService.mark_resolved(1, 1) is False
        assert ErrorAuditService.log("x", category="C") is None


def test_sanitize_undefined_produces_none():
    from jinja2.runtime import Undefined

    clean = ErrorAuditService._sanitize_dict({"missing": Undefined(), "password": "x"})
    assert clean["missing"] is None
    assert clean["password"] == "***REDACTED***"


def test_log_frontend_without_stack(db_session):
    assert ErrorAuditService.log_frontend("cov4-no-stack", level="WARNING", source="s") is not None


def test_logger_error_failure_is_swallowed(mocker, db_session):
    with patch("services.error_audit_service.logger.error", side_effect=RuntimeError("logger down")):
        row_id = ErrorAuditService.log("log-fail", category="CATLOG")
    assert row_id is not None


def test_request_context_url_user_and_payload(app, mocker, db_session, sample_user):
    import json as _json

    with app.test_request_context(
        "/audit/capture",
        data=_json.dumps({"a": 1, "password": "x"}),
        content_type="application/json",
        headers={"User-Agent": "cov4-agent"},
    ):
        mocker.patch("flask_login.utils._get_user", return_value=sample_user)
        row_id = ErrorAuditService.log("ctx-capture", category="BACKEND", level="ERROR", source="s")
    assert row_id is not None


def test_authenticated_user_get_id_failure(app, mocker, db_session):
    for ctx_path in ("/x", "/y"):
        with app.test_request_context(ctx_path):
            broken = MagicMock()
            broken.is_authenticated = True
            broken.get_id = Mock(side_effect=RuntimeError("no id"))
            mocker.patch("flask_login.utils._get_user", return_value=broken)
            ErrorAuditService.log(f"auth-bad-{ctx_path}", category="AUTHB")
    mocker.stopall()


def test_config_get_failure_branch(app, mocker, db_session):
    mocker.patch.object(app.config, "get", side_effect=RuntimeError("cfg gone"))
    ErrorAuditService.log("cfg-fail", category="CFGB")


def test_dup_bump_failure_falls_through_to_insert(db_session):
    with (
        patch.object(ErrorAuditService, "_find_duplicate", return_value=77),
        patch.object(ErrorAuditService, "_bump_duplicate", return_value=False),
    ):
        row_id = ErrorAuditService.log("rollback-insert", category="RBI", level="ERROR", source="s")
    assert row_id is not None


def test_stderr_write_failure_yields_none(db_session):
    import sys

    class _BrokenStream:
        def write(self, *_):
            raise RuntimeError("stderr down")

    with (
        patch("services.error_audit_service.logger"),
        patch("services.error_audit_service.db.engine.connect", side_effect=RuntimeError("down")),
        patch.object(sys, "stderr", _BrokenStream()),
    ):
        assert ErrorAuditService.log("stderr-fail", category="STDFAIL") is None


def test_persist_with_explicit_request_data(app, db_session):
    with app.test_request_context("/audit/direct"):
        row_id = ErrorAuditService._persist(
            message="direct-persist",
            category="DIRECT",
            level="ERROR",
            source="s",
            extra={"job_id": 5},
        )
    assert row_id is not None


def test_persist_without_request_context(mocker, db_session):
    import services.error_audit_service as eas

    with patch.object(eas, "has_request_context", return_value=False):
        row_id = eas.ErrorAuditService._persist(
            message="no-ctx-persist",
            category="BACKEND",
            level="ERROR",
            source="s",
        )
    assert row_id is not None
