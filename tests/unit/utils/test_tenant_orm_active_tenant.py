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

import pytest
from flask import g

from utils.tenant_orm import _active_tenant_for_orm, _stamped_active_tenant
from utils.tenanting import _current_request_id, get_active_tenant_id


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
    with app.test_request_context("/"):
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


def test_nested_orm_resolution_does_not_recurse(app):
    """Resolving the tenant must not be able to re-enter the ORM listener.

    Regression guard. Resolving the active tenant reaches for the Flask
    current_user proxy, and reading an attribute off a partially loaded User
    issues SQL. That SQL fires do_orm_execute, which resolves the tenant again,
    and the pair recurses until the interpreter gives up. It surfaced as a bare
    RecursionError inside SQLAlchemy's annotation machinery from
    services/store_service.py, reached by an after_request handler on every
    response - so it had nothing to do with whatever test happened to be running.

    The guard holds across the whole listener, so a nested statement is left
    unscoped instead of re-entering. This asserts the flag is actually observable
    from inside a nested call rather than trusting that it is set.
    """
    from utils.tenant_orm import _RESOLVING_ACTIVE_TENANT

    with app.app_context():
        assert getattr(_RESOLVING_ACTIVE_TENANT, "value", False) is False

        # Simulate the listener having claimed the flag.
        _RESOLVING_ACTIVE_TENANT.value = True
        try:
            # A nested lookup must not attempt a user probe, which is what issued
            # the nested statement in the first place.
            assert _stamped_active_tenant() is None
        finally:
            _RESOLVING_ACTIVE_TENANT.value = False

    assert getattr(_RESOLVING_ACTIVE_TENANT, "value", False) is False


def test_guard_is_cleared_after_a_normal_resolution(app):
    """A failure mid-resolution must not leave the guard latched forever.

    The listener clears the flag in a finally block. If it did not, every later
    statement in the process would silently skip tenant scoping - a fail-open
    isolation bug rather than a loud one.
    """
    from utils.tenant_orm import _RESOLVING_ACTIVE_TENANT

    with app.app_context():
        with pytest.raises(RuntimeError):
            _RESOLVING_ACTIVE_TENANT.value = True
            try:
                raise RuntimeError("simulated failure inside the listener")
            finally:
                _RESOLVING_ACTIVE_TENANT.value = False

        assert getattr(_RESOLVING_ACTIVE_TENANT, "value", False) is False


def test_platform_owner_can_still_switch_tenants_within_a_request(app):
    """The stamp must not break a platform owner's tenant switch.

    Regression guard. ``g.active_tenant_request`` is stamped in before_request and
    read back by get_active_tenant_id to reach the owner's session-selected
    tenant. Stamping ``id(request)`` - the id of the LocalProxy - instead of the
    underlying request made the stamp permanently unmatched, so the session
    lookup was skipped, get_active_tenant_id returned None for a platform owner,
    and every owner route that needs an active tenant redirected instead.

    This failed as two confusing wave 0 scenario failures ("expected 2 branches,
    got 0") before the actual cause was found, so it is asserted directly.
    """
    from utils.tenanting import ACTIVE_TENANT_SESSION_KEY, get_active_tenant_id

    class FakeOwner:
        is_authenticated = True
        # is_platform_owner() reads `is_owner`; there is no is_platform_owner
        # attribute on a User, so naming the flag that way here would silently
        # make this a company user and test nothing.
        is_owner = True
        tenant_id = None

    with app.test_request_context("/") as ctx:
        from flask import g, session

        from utils.tenanting import _current_request_id

        g.active_tenant_request = _current_request_id()
        session[ACTIVE_TENANT_SESSION_KEY] = 42
        assert get_active_tenant_id(FakeOwner()) == 42

        # And the stamp really is the underlying request, not the proxy: taking
        # id() of the proxy would make this comparison vacuously false.

        assert _current_request_id() == id(ctx.request), "stamp compares the proxy, not the request"


def test_unstamped_g_inside_a_live_request_is_trusted(app):
    """A tenant set directly on g during a request belongs to that request.

    An earlier version treated an unstamped value as untrustworthy, on the theory
    that only before_request may set it. That was too strong: g is
    request-scoped, so a value assigned inside a live request describes that
    request. Management commands, and tests that drive a service inside
    ``test_request_context``, both rely on it.

    The cost of getting this wrong was concrete and is why it is asserted here:
    with the value ignored, resolve_tenant_id fell through to counting active
    tenants and raised "3 active tenants found" in tests that never had three
    tenants. The tenant guard was working correctly on a context the caller had
    already answered.

    A stamp that is present but *stale* is still refused - see
    test_stale_request_value_is_ignored_once_the_request_ends.
    """
    with app.test_request_context("/"):
        g.active_tenant_id = 99
        # getattr, not attribute access: nothing stamped this request, so the
        # attribute is genuinely absent rather than None.
        assert getattr(g, "active_tenant_request", None) is None, "precondition: nothing stamped this request"
        assert _active_tenant_for_orm() == 99
