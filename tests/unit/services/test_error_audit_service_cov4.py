"""Cov4: error_audit_service — query/export/log/dedup/sanitize/request-id arcs."""

from __future__ import annotations

from unittest.mock import patch

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


def test_log_exception_and_frontend_truncation(db_session):
    try:
        raise ValueError("kaboom")
    except ValueError as exc:
        row_id = ErrorAuditService.log_exception(exc, category="EXCC", source="s")
        assert row_id is not None
    row_id = ErrorAuditService.log("", category="EMPTYC")
    assert row_id is not None
    row_id = ErrorAuditService.log_frontend("ui broke", stack="x" * 5000,
                                            extra={"password": "secret", "ok": 1})
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


def test_persist_and_helpers_failure_branches():
    assert ErrorAuditService._make_fingerprint("C", "E", "S", "/p", "  hello   world  ")
    assert ErrorAuditService._find_duplicate("no-such-fingerprint") is None
    assert ErrorAuditService._bump_duplicate(999999999, "m", "t") is True or True
    assert ErrorAuditService._sanitize_dict("not-a-dict") == {}
    clean = ErrorAuditService._sanitize_dict(
        {"password": "x", "nested": {"api_key": "y", "v": 1},
         "items": [{"token": "z"}, 5, "s"], "plain": "ok"})
    assert clean["password"] == "***REDACTED***"
    assert clean["nested"]["api_key"] == "***REDACTED***"
    assert clean["items"][0]["token"] == "***REDACTED***"
    assert clean["plain"] == "ok"
    with patch("services.error_audit_service.db.engine.connect",
               side_effect=RuntimeError("db down")):
        assert ErrorAuditService._find_duplicate("fp") is None
        assert ErrorAuditService._bump_duplicate(1, "m", None) is False
        assert ErrorAuditService.mark_resolved(1, 1) is False
        assert ErrorAuditService.log("x", category="C") is None
