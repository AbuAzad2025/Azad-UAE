"""Phase 2, end to end: routes/payments.py must not put technical text on the page.

The unit-level guarantees live in tests/unit/utils/test_error_governance.py.
This proves the route actually renders a governed message when the archive
raises a database error.

The assertion is on the FLASH rather than on the rendered page: the redirect
target (the receipts list) needs template context this minimal app does not
install, and the receipts page is not what is under test. What matters is the
message the user is shown.
"""

from unittest.mock import patch

# ArchiveService is imported inside the route function, so it is not an
# attribute of the routes module: patch the class where it is defined.
_ARCHIVE_RAISES = "services.archive_service.ArchiveService.archive_record"


def _fake_payment():
    return type(
        "FakePayment",
        (),
        {
            "branch_id": None,
            "id": 1,
            "payment_number": "PAY-1",
            "cheque_id": None,
            "supplier_id": None,
            "purchase_id": None,
        },
    )()


def _flashed(client):
    """The messages the user would see.

    Flask stores each flash as a (category, message) pair - the category comes
    first, so unpacking it as (message, category) silently yields the category.
    """
    with client.session_transaction() as sess:
        flashes = sess.pop("_flashes", [])
    return [message for _category, message in flashes]


def _client(app_factory, bypass_permission_auth):
    from routes.payments import payments_bp
    from routes.public import public_bp

    return app_factory(payments_bp, public_bp).test_client()


def test_an_archive_failure_never_shows_sql(app_factory, bypass_permission_auth):
    client = _client(app_factory, bypass_permission_auth)
    boom = 'duplicate key value violates unique constraint "uq_gl_journal_entries_tenant_number"'

    with (
        patch(_ARCHIVE_RAISES, side_effect=RuntimeError(boom)),
        patch("routes.payments.tenant_get_or_404", return_value=_fake_payment()),
        patch("utils.decorators.branch_scope_id", return_value=None),
    ):
        resp = client.post("/payments/payments/1/archive", follow_redirects=False)

    assert resp.status_code == 302, "the route must still redirect, not 500"
    shown = " ".join(_flashed(client))
    assert shown, "the user must be told something happened"
    assert "uq_gl_journal_entries_tenant_number" not in shown, "SQL constraint name leaked to the page"
    assert "duplicate key value" not in shown, "raw database message leaked to the page"
    assert "RuntimeError" not in shown, "Python exception leaked to the page"


def test_a_delete_failure_never_shows_sql(app_factory, bypass_permission_auth):
    client = _client(app_factory, bypass_permission_auth)
    boom = 'null value in column "amount" of relation "receipts" violates not-null constraint'

    with (
        patch("routes.payments.PaymentService.delete_payment", side_effect=RuntimeError(boom)),
        patch("routes.payments.tenant_get_or_404", return_value=_fake_payment()),
        patch("utils.decorators.branch_scope_id", return_value=None),
    ):
        resp = client.post("/payments/payments/1/delete", follow_redirects=False)

    assert resp.status_code == 302
    shown = " ".join(_flashed(client))
    assert "not-null constraint" not in shown, "raw database message leaked to the page"
    assert 'relation "receipts"' not in shown, "table name leaked to the page"
    assert "RuntimeError" not in shown


def test_a_system_failure_carries_a_reference(app_factory, bypass_permission_auth):
    """A reference the user can quote is what makes the log entry findable."""
    client = _client(app_factory, bypass_permission_auth)

    with (
        patch(_ARCHIVE_RAISES, side_effect=RuntimeError("boom")),
        patch("routes.payments.tenant_get_or_404", return_value=_fake_payment()),
        patch("utils.decorators.branch_scope_id", return_value=None),
    ):
        client.post("/payments/payments/1/archive", follow_redirects=False)

    shown = " ".join(_flashed(client))
    assert "رقم المرجع" in shown, f"no reference to quote back to support: {shown!r}"


def test_the_route_logs_the_trace_it_hides(app_factory, bypass_permission_auth, caplog):
    """Hiding it from the page is only half the job; support needs the trace."""
    import logging

    client = _client(app_factory, bypass_permission_auth)

    with caplog.at_level(logging.ERROR):
        with (
            patch(_ARCHIVE_RAISES, side_effect=RuntimeError("boom-in-the-log")),
            patch("routes.payments.tenant_get_or_404", return_value=_fake_payment()),
            patch("utils.decorators.branch_scope_id", return_value=None),
        ):
            client.post("/payments/payments/1/archive", follow_redirects=False)

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "archive payment 1" in logged, f"the log entry must name the operation: {logged!r}"
    assert any(record.exc_info for record in caplog.records), "the traceback must be logged"
