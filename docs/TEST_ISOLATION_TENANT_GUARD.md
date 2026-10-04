# Test isolation: the tenant guard must not trust `g` outside a request

## The failure this prevents

Writing S-07 (cash sale at the till) and S-09 (multi-tender) failed at fixture
setup, on fixtures that have nothing to do with a sale:

    utils.tenant_orm.TenantIsolationError: Cross-tenant INSERT on Branch:
    obj.tenant_id=3 != active_tenant=1

`demo_branch` simply creates a branch for `demo_tenant` (id 3). It was rejected
against tenant **1**, which belonged to a user created by an earlier fixture in
the same test.

## Root cause

`tests/conftest.py::db_session` wraps the whole test in `with app.app_context():`

    @pytest.fixture
    def db_session(app):
        with app.app_context():
            ...
            yield session
            ...

Flask's `RequestContext.push()` **reuses an already-pushed app context** for the
same app instead of pushing a fresh one:

    app_ctx = _cv_app.get(None)
    if app_ctx is None or app_ctx.app is not self.app:
        app_ctx = self.app.app_context()
        app_ctx.push()

So while `db_session` is alive, every `client.get(...)` / `client.post(...)` in
the test reuses that one app context, and therefore the same `g`. The factory's
`before_request` sets `g.active_tenant_id = get_active_tenant_id(_cu)` per
request, but because `g` is shared across those requests, the value from the
login performed in `pos_cashier` was still on `g` when `stocked_product` went on
to build the demo tenant's rows.

`utils/tenant_orm.py::_active_tenant_for_orm` read `g.active_tenant_id`
unconditionally, so the write guard validated against a tenant from a request that
had already ended. Hence 3 vs 1, and hence the order dependence.

Two things had been ruled out first, and it is worth recording why, because both
look plausible and cost time:

- **The Flask cookie session.** `client` is function-scoped and already clears
  `session_transaction()` on teardown, so the session was not the carrier.
  Clearing cookies again changed nothing.
- **An unbound `current_user` proxy.** `utils/tenanting.py::_resolve_user` wraps
  the lookup in `try/except RuntimeError` and returns `None`, so outside a request
  it degrades correctly. An earlier hypothesis blamed this; it was wrong.

## The fix

Gate the `g` lookup on it belonging to the request in flight.

    # utils/tenant_orm.py::_active_tenant_for_orm
    from flask import g, has_request_context

    if has_request_context():
        g_tid = getattr(g, "active_tenant_id", None)
        if g_tid is not None:
            return int(g_tid)

    from utils.tenanting import get_active_tenant_id

    return get_active_tenant_id()

Why this is safe and not a loosening:

- **In production nothing changes.** Every ORM flush happens inside a request, so
  `has_request_context()` is `True` and `g` is still used. The reason `g` was
  preferred in the first place - re-resolving `current_user` at execute time can
  return `None` for lazy loads and nested queries, which used to inject
  `tenant_id < 0` and silently empty tenant-scoped lists - is a concern that only
  arises *within* a request. That protection is fully preserved.
- **Outside a request there is nothing to enforce.** No request means no active
  tenant, so the guard must not invent one. `get_active_tenant_id()` resolves to
  `None` there via `_resolve_user`'s `RuntimeError` handling.
- **The escape hatch is unchanged.** Code that genuinely writes cross-tenant
  outside a request (provisioning, migrations, imports) still uses the documented
  `without_tenant_scope()`.

The same defect applied beyond the test harness. A CLI command or a background job
that holds an app context open while running several tenants' work would have had
the first tenant's id pinned onto `g` and enforced for all of them.

## Regression coverage

`tests/unit/utils/test_tenant_orm_active_tenant.py`:

- a `g.active_tenant_id` left over from an earlier request is ignored once that
  request has ended, so a write for a different tenant is not rejected against it
- `g.active_tenant_id` is still honoured inside a live request context, so the
  in-request lazy-load protection is unchanged
- `get_active_tenant_id()` returns `None` with an app context open but no request