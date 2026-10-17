"""Phase 3, end to end: routes/cheques.py must not put technical text on the page,
and a business refusal must read as guidance rather than a crash.

The generic guarantees live in tests/unit/utils/test_error_governance.py.
This file is the cheque-specific proof.
"""

import logging
from unittest.mock import patch

# process_cheque_* are imported into the routes module at import time, so they
# are attributes of routes.cheques and can be patched there.
_DEPOSIT_RAISES = "routes.cheques.process_cheque_deposit"
_CLEAR_RAISES = "routes.cheques.process_cheque_clear"


def _flashed(client):
    """The messages the user would see.

    Flask stores each flash as a (category, message) pair - the category comes
    first, so unpacking it as (message, category) silently yields the category.
    """
    with client.session_transaction() as sess:
        flashes = sess.pop("_flashes", [])
    return [message for _category, message in flashes]


def _client(app_factory, bypass_permission_auth):
    from routes.cheques import cheques_bp
    from routes.public import public_bp

    return app_factory(cheques_bp, public_bp).test_client()


def _cheque(status="pending", cheque_type="incoming"):
    return type(
        "FakeCheque",
        (),
        {
            "id": 7,
            "status": status,
            "status_ar": "قيد التحصيل",
            "cheque_type": cheque_type,
            "cheque_bank_number": "CHQ-1",
            "branch_id": None,
            "tenant_id": 1,
        },
    )()


def _scope(app):
    return (
        patch("routes.cheques._get_cheque_or_404", return_value=_cheque()),
        patch("routes.cheques._ensure_cheque_scope", return_value=True),
        patch("utils.decorators.branch_scope_id", return_value=None),
        patch("utils.tenanting.get_active_tenant_id", return_value=1),
    )


def test_a_deposit_failure_never_shows_sql(app_factory, bypass_permission_auth):
    client = _client(app_factory, bypass_permission_auth)
    boom = 'duplicate key value violates unique constraint "uq_gl_journal_entries_tenant_number"'
    get_or_404, scope, branch, tenant = _scope(app_factory)

    with get_or_404, scope, branch, tenant, patch(_DEPOSIT_RAISES, side_effect=RuntimeError(boom)):
        resp = client.post("/cheques/7/deposit", follow_redirects=False)

    assert resp.status_code == 302, "the route must redirect, not 500"
    shown = " ".join(_flashed(client))
    assert shown, "the operator must be told something happened"
    for leak in ("uq_gl_journal_entries_tenant_number", "duplicate key value", "RuntimeError", "Traceback"):
        assert leak not in shown, f"{leak!r} leaked to the page"


def test_a_system_failure_carries_a_reference(app_factory, bypass_permission_auth):
    """The reference is what makes the log entry findable from the page."""
    client = _client(app_factory, bypass_permission_auth)
    get_or_404, scope, branch, tenant = _scope(app_factory)

    with get_or_404, scope, branch, tenant, patch(_DEPOSIT_RAISES, side_effect=RuntimeError("boom")):
        client.post("/cheques/7/deposit", follow_redirects=False)

    assert "رقم المرجع" in " ".join(_flashed(client))


def test_a_system_failure_logs_the_trace_it_hides(app_factory, bypass_permission_auth, caplog):
    client = _client(app_factory, bypass_permission_auth)
    get_or_404, scope, branch, tenant = _scope(app_factory)

    with caplog.at_level(logging.ERROR), get_or_404, scope, branch, tenant:
        with patch(_DEPOSIT_RAISES, side_effect=RuntimeError("boom-in-the-log")):
            client.post("/cheques/7/deposit", follow_redirects=False)

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "cheque deposit 7" in logged, f"the log entry must name the operation: {logged!r}"
    assert any(record.exc_info for record in caplog.records), "the traceback must be logged"


def test_a_state_refusal_reads_as_guidance_not_a_crash(app_factory, bypass_permission_auth):
    """A business refusal is shown as written, and never looks like a crash."""
    from utils.error_messages import BusinessRuleError, ErrorCategory

    client = _client(app_factory, bypass_permission_auth)
    cheque = _cheque(status="cancelled")
    refusal = BusinessRuleError(
        "لا يمكن تأكيد صرف الشيك في حالته الحالية (ملغي).\nالحالات التي تسمح بهذه العملية: مُودع في البنك.",
        category=ErrorCategory.STATE,
    )

    with (
        patch("routes.cheques._get_cheque_or_404", return_value=cheque),
        patch("routes.cheques._ensure_cheque_scope", return_value=True),
        patch("utils.decorators.branch_scope_id", return_value=None),
        patch(_CLEAR_RAISES, side_effect=refusal),
    ):
        resp = client.post("/cheques/7/clear", follow_redirects=False)

    assert resp.status_code == 302
    shown = " ".join(_flashed(client))
    assert "لا يمكن تأكيد صرف" in shown, f"the business message must be shown: {shown!r}"
    assert "رقم المرجع" not in shown, "a business refusal must not masquerade as a system failure"


def test_no_raw_exception_reaches_a_cheque_flash():
    """Static guard on the source: this is the defect the whole layer prevents."""
    from pathlib import Path

    source = Path("routes/cheques.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("#"))

    offenders = [
        line.strip()
        for line in code.splitlines()
        if "flash(" in line and ("str(e)" in line or "str(exc)" in line or "repr(e)" in line)
    ]
    assert not offenders, f"raw exception text still reaches the page: {offenders}"
    assert "sys.stderr.write" not in code, "stderr bypasses the configured log handlers"
    assert "traceback.print_exc()" not in code


def test_every_lifecycle_handler_goes_through_the_governed_path():
    from pathlib import Path

    source = Path("routes/cheques.py").read_text(encoding="utf-8")
    assert "_refuse(" in source, "the route must funnel failures through _refuse()"
    # deposit, clear, bounce, cancel, delete, restore, create, edit
    assert source.count("_refuse(e") >= 8, (
        f"each lifecycle handler must report through _refuse(); found {source.count('_refuse(e')} call sites"
    )
