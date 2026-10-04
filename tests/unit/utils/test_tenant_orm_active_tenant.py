"""The ORM write guard must resolve the active tenant per request, not per app context.

`g.active_tenant_id` is stamped by the factory's `before_request`. An app context
can outlive the request that stamped it - Flask reuses an already-pushed app
context rather than pushing a new one, so `g` is the same object for every
request made while that context is open - and the stamped value survives after
the request ends. The guard was reading it unconditionally, so a write made
after that request was validated against a tenant it had nothing to do with.

See docs/TEST_ISOLATION_TENANT_GUARD.md for the full write-up.

These use the real application rather than a bare ``Flask(...)``: resolving the
tenant falls through ``_resolve_user`` -> ``current_user``, which needs the app's
login manager to exist at all.
"""

from flask import g

from utils.tenant_orm import _active_tenant_for_orm
from utils.tenanting import _current_request_id
from utils.tenanting import get_active_tenant_id, without_tenant_scope


def test_flask_reuses_the_pushed_app_context_for_requests(app):
    """Precondition for the whole issue, asserted so the harness cannot drift.

    If a future Flask version starts pushing a fresh app context per request, the
    leak this file guards against disappears on its own and the fix becomes
    unnecessary. Failing loudly beats a fix whose premise quietly changed.
    """
    with app.app_context():
        outer = g
        with app.test_request_context("/"):
            assert g is outer, "Flask pushed a new app context for the request"

        assert g is outer, "Flask popped the outer app context along with the request"


def test_live_request_context_is_honoured(app):
    """Inside a request the guard still trusts g.

    This is what the original code was written for: re-resolving current_user at
    ORM-execute time can return None for lazy loads and nested queries, which
    used to inject `tenant_id < 0` and silently empty every tenant-scoped list.
    It must not regress.
    """
    with app.test_request_context("/") as ctx:
        g.active_tenant_request = _current_request_id()
        g.active_tenant_id = 7
        assert _active_tenant_for_orm() == 7


def test_stale_request_value_is_ignored_once_the_request_ends(app):
    """The regression itself.

    Same shape as the wave 1 fixtures: an app context held open across a login,
    then a write for a different tenant once the request is over.
    """
    with app.app_context():
        with app.test_request_context("/"):
            g.active_tenant_request = _current_request_id()
            g.active_tenant_id = 1

        # The leak is real, and that is the point: the value is still sitting there.
        assert g.active_tenant_id == 1

        # But the guard must not enforce it any more.
        assert _active_tenant_for_orm() is None


def test_get_active_tenant_id_is_none_outside_a_request(app):
    """No request means no active tenant, even with the app context open."""
    with app.app_context():
        assert get_active_tenant_id() is None


def test_tenanting_helper_still_locks_a_company_user_to_their_own_tenant(app):
    """Passing a user explicitly is untouched by the no-request behaviour."""

    class FakeUser:
        is_authenticated = True
        is_platform_owner = False
        tenant_id = 42

    with app.app_context():
        assert get_active_tenant_id(FakeUser()) == 42


def test_without_tenant_scope_remains_the_documented_bypass(app):
    """Cross-tenant writes outside a request keep using the escape hatch."""
    with app.app_context():
        with without_tenant_scope():
            assert _active_tenant_for_orm() is None

def test_unstamped_g_is_not_trusted(app):
    """A g that was never stamped by before_request carries no authority.

    Nothing sets active_tenant_request for a request that never reached
    before_request, so a value left on g from elsewhere must not be enforced.
    """
    with app.test_request_context("/"):
        g.active_tenant_id = 99
        assert _active_tenant_for_orm() is None
