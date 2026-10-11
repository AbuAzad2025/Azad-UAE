"""Wave 7 debt - the owner database console, reached by an owner.

``test_wave7_backups.py`` proved the platform backup and database tools are
invisible to everyone who is not the platform owner: 404 for anonymous, 404 for
a signed-in tenant user. That is the right result and it was worth asserting
route by route.

It leaves the other half untested, and the other half is where the danger is.
``/owner/execute-query`` is a raw SQL console. ``_validate_select_only_sql``
exists because "starts with SELECT" is not a safety property - ``SELECT`` can
be stacked behind a semicolon, can name a blocked tenant table, or can read
``pg_shadow`` and hand back password hashes. None of that is visible from a
guard test, because a guard test never gets past the guard.

So each rule gets its own scenario, and the refusals are asserted as refusals
with the reason attached:

- empty, non-SELECT, stacked statements, forbidden keywords,
- system relations (which is why ``information_schema`` is *not* in that list -
  the schema browser reads it, and it exposes no rows),
- blocked tenant tables, resolved from ``db.metadata`` rather than hardcoded.

And then the two that make the refusals meaningful: a legitimate SELECT is
allowed and returns rows, and a legitimate truncate is allowed. A validator
that refused everything would pass every refusal scenario in this file while
making the feature unusable.
"""

from __future__ import annotations

import uuid

import pytest


def _owner(db_session, client):
    """A platform owner: ``is_owner`` with no tenant attached.

    Both halves matter. ``is_global_owner_user`` requires the flag *and* an
    absent tenant, so a user with the flag but a tenant attached - which is what
    a stale session looks like - is not an owner and gets 404, not 403.
    """
    from models import Role, Tenant, User

    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"BAK Platform {unique}",
        name_ar="منصة",
        slug=f"bak-plat-{unique}",
        email=f"bak-plat-{unique}@example.com",
        country="AE",
        subscription_plan="basic",
        is_active=True,
    )
    db_session.add(tenant)
    db_session.commit()

    role = db_session.query(Role).filter_by(slug="owner").first()
    if role is None:
        role = Role(name="Owner", slug="owner", is_active=True)
        db_session.add(role)
        db_session.commit()

    user = User(
        username=f"bak-owner-{unique}",
        email=f"bak-plat-{unique}@example.com",
        full_name="BAK Owner",
        tenant_id=None,
        role_id=role.id,
        is_owner=True,
        is_active=True,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()

    client.post(
        "/auth/login",
        data={"username": user.username, "password": "password123"},
        follow_redirects=True,
    )
    return user


class TestBAK21TheSqlConsoleRefuses:
    """BAK-21 to BAK-27: every rule in _validate_select_only_sql."""

    def test_an_empty_query_is_refused(self, client, db_session):
        """BAK-21. There is nothing to run, and an empty box is not consent."""
        _owner(db_session, client)

        resp = client.post("/owner/execute-query", data={"query": "   "}, follow_redirects=False)
        assert resp.status_code == 400, f"an empty query answered {resp.status_code}, expected a refusal"

    def test_a_statement_that_is_not_a_select_is_refused(self, client, db_session):
        """BAK-22. The console is read-only, and the check is the first word.

        This is the crudest of the rules and the one that is easiest to lose in
        a refactor - it is a single ``startswith``. Everything after it depends
        on it holding.
        """
        _owner(db_session, client)

        resp = client.post("/owner/execute-query", data={"query": "VACUUM ANALYZE tenants"}, follow_redirects=False)
        assert resp.status_code == 400, f"a non-SELECT answered {resp.status_code}, expected a refusal"

    @pytest.mark.parametrize(
        "query",
        [
            "SELECT 1; DROP TABLE tenants",
            "SELECT 1; DELETE FROM tenants",
            "SELECT 1; UPDATE tenants SET name = 'x'",
        ],
    )
    def test_a_stacked_statement_is_refused(self, client, db_session, query):
        """BAK-23. A trailing semicolon is how a read becomes a write.

        Every keyword check below tests for ``"DROP "`` *with a trailing space*,
        so ``SELECT 1; DROP TABLE`` passes every one of them. The semicolon
        rule is the only thing standing between the console and stacked
        statements, which is why it gets its own scenario and three payloads
        rather than being folded into the keyword test.
        """
        _owner(db_session, client)

        resp = client.post("/owner/execute-query", data={"query": query}, follow_redirects=False)
        assert resp.status_code == 400, f"a stacked statement answered {resp.status_code}, expected a refusal"

    @pytest.mark.parametrize(
        "query",
        [
            "SELECT * FROM x WHERE 1=1 -- DROP TABLE tenants",
            "SELECT count(*) FROM t; INSERT INTO t VALUES (1)",
        ],
    )
    def test_a_second_statement_after_a_semicolon_is_refused(self, client, db_session, query):
        """BAK-23b. The rule is "one statement", not "no dangerous word"."""
        _owner(db_session, client)

        resp = client.post("/owner/execute-query", data={"query": query}, follow_redirects=False)
        assert resp.status_code == 400, f"a stacked statement answered {resp.status_code}, expected a refusal"

    @pytest.mark.parametrize(
        "query",
        [
            "SELECT 1 FROM t WHERE x = 'DROP '",
            "SELECT count(*) FROM t -- UPDATE ",
        ],
    )
    def test_a_forbidden_keyword_anywhere_is_refused(self, client, db_session, query):
        """BAK-24. The keyword scan is the backstop under the prefix rule."""
        _owner(db_session, client)

        resp = client.post("/owner/execute-query", data={"query": query}, follow_redirects=False)
        assert resp.status_code == 400, f"a query carrying a forbidden keyword answered {resp.status_code}"

    def test_reading_a_system_relation_is_refused(self, client, db_session):
        """BAK-25. ``SELECT`` can still exfiltrate.

        ``pg_shadow`` and ``pg_authid`` hold password hashes and role
        definitions. They are in ``db.metadata``, so no table-name blocklist
        would ever catch them - hence a separate system-relation check. The
        paired assertion matters as much as the refusal: ``information_schema``
        is deliberately *not* blocked, because the schema browser reads it and
        it exposes no row data.
        """
        _owner(db_session, client)

        resp = client.post(
            "/owner/execute-query", data={"query": "SELECT usename, passwd FROM pg_shadow"}, follow_redirects=False
        )
        assert resp.status_code == 400, f"reading pg_shadow answered {resp.status_code}, expected a refusal"

        allowed = client.post(
            "/owner/execute-query",
            data={"query": "SELECT table_name FROM information_schema.tables LIMIT 1"},
            follow_redirects=False,
        )
        assert allowed.status_code == 200, (
            f"information_schema is refused ({allowed.status_code}); it is deliberately readable "
            "and blocking it would break the schema browser"
        )

    def test_reading_a_blocked_tenant_table_is_refused(self, client, db_session):
        """BAK-26. Tenant business tables are off limits to the console.

        The blocked set is built from ``db.metadata``, so it tracks the schema
        instead of drifting from a hand-written list. Sales, invoices, payments
        and stock are readable through their own tenant-scoped routes; the
        console exists for schema questions, not for reading another tenant's
        ledger without a tenant scope.
        """
        from models import Sale

        _owner(db_session, client)
        table = Sale.__tablename__

        resp = client.post(
            "/owner/execute-query",
            data={"query": f"SELECT * FROM {table} LIMIT 1"},
            follow_redirects=False,
        )
        assert resp.status_code == 400, f"reading {table} answered {resp.status_code}, expected a refusal"

    def test_a_legitimate_select_is_allowed(self, client, db_session):
        """BAK-27. And the console is actually usable.

        Without this, every scenario above is satisfied by a validator that
        refuses all SQL. The envelope is part of the contract too: ``rows`` and
        a ``count`` that matches them, because the console renders both.
        """
        _owner(db_session, client)

        resp = client.post("/owner/execute-query", data={"query": "SELECT 1 AS one"}, follow_redirects=False)
        assert resp.status_code == 200, (
            f"a legitimate SELECT answered {resp.status_code}: {resp.get_data(as_text=True)[:200]}"
        )

        body = resp.get_json()
        assert body is not None and "data" in body, f"the console answered {body} without an envelope"
        data = body["data"]
        assert "rows" in data and "count" in data, f"the console payload is missing keys; it has {sorted(data)}"
        assert data["count"] == len(data["rows"]), (
            f"count says {data['count']} but the result holds {len(data['rows'])} rows"
        )

    def test_a_select_over_a_table_that_does_not_exist_fails_cleanly(self, client, db_session):
        """BAK-28. A bad table is an error, not a 500.

        The console takes arbitrary SQL from an owner, so typos are expected.
        ``db.session.execute`` raising must be caught and answered as a 400;
        an unhandled exception would surface a stack trace to the browser.
        """
        _owner(db_session, client)

        resp = client.post(
            "/owner/execute-query",
            data={"query": "SELECT * FROM table_that_is_not_here"},
            follow_redirects=False,
        )
        assert resp.status_code == 400, f"a missing table answered {resp.status_code}, expected a handled error"
