# Test isolation: the tenant guard reads `g.active_tenant_id`, not the session

## The failure this prevents

Writing S-07 and S-09 (cash sale at the till, multi-tender) failed with:

    utils.tenant_orm.TenantIsolationError: Cross-tenant INSERT on Branch:
    obj.tenant_id=3 != active_tenant=1

on fixtures that have nothing to do with a sale. `sample_branch` simply creates
a branch, and it raised while being set up.

## Root cause

The write guard resolves the active tenant in this order
(`utils/tenant_orm.py:_active_tenant_for_orm`):

1. `g.active_tenant_id` if set
2. otherwise `utils.tenanting.get_active_tenant_id()` with **no argument**

Step 2 is the problem. Called with no argument, `get_active_tenant_id` does
`_resolve_user(None)`, which reaches for `current_user`. That is a Flask
LocalProxy. **Outside a request context it does not evaluate to `None` - it
reaches whatever the proxy was last bound to**, and `_resolve_user` passes that
value on. The branch of the function that returns `None` for an unauthenticated
user is never reached, because a stale bound value looks authenticated.

So a tenant id left over from a previous request is used to validate a write
that happens in a fixture, outside any request. The comparison is against a
tenant that has nothing to do with the row being written, and it fails.

`tests/conftest.py:client` is already function-scoped and clears
`session_transaction()` on teardown, so the Flask cookie session is not the
carrier. The leak is in the unbound `current_user` proxy, not in the session
cookie - which is why clearing cookies in a fixture did not help, and why the
failure depended on test order rather than reproducing in isolation.

## The fix

Make the no-argument path honest about having no request context, so it returns
`None` instead of a stale proxy value:

    # utils/tenanting.py, at the top of get_active_tenant_id, before
    # _resolve_user is called with nothing:
    if user is None and not has_request_context():
        return None

There is no legitimate caller that wants a tenant id outside a request: every
real path either passes a user explicitly or runs inside a request. A fixture
that genuinely needs to write cross-tenant rows already has
`without_tenant_scope()` for that, which is the documented mechanism.

## Why it belongs in production code and not only in the tests

`get_active_tenant_id()` is called from the ORM event listeners on every flush.
Making it return `None` when there is no request means:

- writes made outside a request (CLI commands, migrations, background jobs,
  test fixtures) are no longer validated against a phantom tenant
- the existing `without_tenant_scope()` escape hatch remains the explicit,
  auditable way to bypass the guard

Without this, any code path that writes tenant-scoped rows outside a request -
a management command, a data migration, a fixture - either fails spuriously
against whatever tenant was last active or, worse, silently passes because the
stale value happened to match.

## Not yet verified

The one-line change above is the diagnosis reached by reading the resolution
order. It has **not** been applied and its effect has not been measured, because
it was identified at the point this session ran out of budget. Applying it should
make S-07 and S-09 collectable; that is the first thing to check, not an
assumption.

A regression guard belongs with it: a test that writes a tenant-scoped row with
no request context and asserts it is not rejected against a stale tenant, and a
second that asserts `get_active_tenant_id()` returns `None` outside a request.