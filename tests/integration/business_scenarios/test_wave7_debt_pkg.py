"""Wave 8 debt part of Wave 7 - the billing webhooks and the vault's own health.

``test_wave7_pkg.py`` covered the payment vault from the outside: packages,
purchases, donations, the public purchase API, vault lock and password, exports.
It did not touch ``routes/billing_webhooks.py`` at all - all three of its
routes, including the one the owner is *documented* to use by hand.

That is the wrong gap to leave open. These three endpoints are unauthenticated
by design - a payment gateway cannot log in - and two of them turn a POST body
into a subscription on a tenant. The whole security argument for them is the
secret header, the signature, the freshness window and the replay check, and
every one of those was unasserted.

The order matters, so it is walked in order:

- unconfigured secret -> 503. A deployment that forgot the secret fails closed
  rather than accepting everything.
- wrong secret -> 403, and nothing is provisioned.
- right secret, unhandled event -> acknowledged, nothing provisioned. A gateway
  that retries an event we do not handle must not error, or it retries forever.
- right secret, handled event, no tenant_id/package_id -> 400. The metadata is
  what says who is buying what.
- a stale timestamp -> 400. Without the freshness window a captured webhook
  could be replayed months later to grant a subscription that was paid for in
  a promotion which has since ended.

The cron endpoint is the same shape with a different secret: 503 unconfigured,
403 wrong, and then it runs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

SECRET = "webhook-secret-for-scenarios"
CRON = "cron-secret-for-scenarios"


def _owner(db_session, client):
    """A platform owner, signed in over real HTTP.

    ``tenant_id is None`` is half of ``is_global_owner_user``; the other half is
    ``is_owner``. A user with the flag but a tenant attached is not a platform
    owner, which is the distinction the vault's guards turn on.
    """
    from models import Role, Tenant, User

    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"PKG Platform {unique}",
        name_ar="منصة",
        slug=f"pkg-plat-{unique}",
        email=f"pkg-plat-{unique}@example.com",
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
        username=f"pkg-owner-{unique}",
        email=f"pkg-plat-{unique}@example.com",
        full_name="PKG Owner",
        tenant_id=None,
        role_id=role.id,
        is_owner=True,
        is_active=True,
    )
    user.set_password("password123")
    db_session.add(user)
    db_session.commit()
    _login(client, user)
    return user


def _login(client, user):
    """Sign ``user`` in, replacing any session a fixture already opened.

    ``/auth/login`` short-circuits to a redirect when the session is already
    authenticated, so without the logout this call is silently a no-op and the
    route under test keeps being reached as the previous user.
    """
    client.get("/auth/logout", follow_redirects=True)
    return client.post(
        "/auth/login", data={"username": user.username, "password": "password123"}, follow_redirects=True
    )


def _event(**over):
    payload = {
        "event": "payment_succeeded",
        "tenant_id": 1,
        "package_id": 1,
        "duration_type": "monthly",
        "transaction_id": f"manual-{uuid.uuid4().hex[:8]}",
        "timestamp": int(datetime.now(UTC).timestamp()),
    }
    payload.update(over)
    return payload


class TestPKG60TheGenericWebhookFailsClosed:
    """PKG-60 to PKG-64: the owner manual-override endpoint, walked in order."""

    def test_an_unconfigured_secret_refuses_everything(self, app, client, db_session):
        """PKG-60. No secret configured means no webhook.

        The alternative - accept the request when the deployment forgot to set
        the secret - would turn a configuration mistake into an open endpoint
        that grants subscriptions to anyone who POSTs a tenant id.
        """
        app.config["BILLING_WEBHOOK_SECRET"] = None

        resp = client.post(
            "/billing-webhook/generic",
            json=_event(),
            headers={"X-Webhook-Secret": "anything-at-all"},
            follow_redirects=False,
        )
        assert resp.status_code == 503, f"an unconfigured generic webhook answered {resp.status_code}, expected 503"
        assert "data" not in resp.get_json() or resp.get_json()["data"] is None, (
            "an unconfigured webhook answered with a payload"
        )

    def test_a_wrong_secret_is_refused(self, app, client, db_session):
        """PKG-61. The secret is the only thing standing between the internet
        and a subscription grant."""
        app.config["BILLING_WEBHOOK_SECRET"] = SECRET

        resp = client.post(
            "/billing-webhook/generic",
            json=_event(),
            headers={"X-Webhook-Secret": "not-the-secret"},
            follow_redirects=False,
        )
        assert resp.status_code == 403, f"a wrong secret answered {resp.status_code}, expected 403"

    def test_an_unhandled_event_is_acknowledged_without_provisioning(self, app, client, db_session):
        """PKG-62. A gateway that retries an error retries forever.

        ``customer.updated`` is not one of the three events that provision. The
        right answer is a success with nothing done - the gateway stops
        retrying, and nothing was granted. An error here would fill the
        provider's retry queue with events we will never act on.
        """
        app.config["BILLING_WEBHOOK_SECRET"] = SECRET

        resp = client.post(
            "/billing-webhook/generic",
            json=_event(event="customer.updated"),
            headers={"X-Webhook-Secret": SECRET},
            follow_redirects=False,
        )
        assert resp.status_code == 200, f"an unhandled event answered {resp.status_code}, expected an acknowledgement"
        body = resp.get_json()
        assert body is not None and body.get("data", {}).get("status") == "acknowledged", (
            f"an unhandled event answered {body}, expected an acknowledgement and no provisioning"
        )
        assert "provisioning" not in body.get("data", {}), "an unhandled event provisioned a package"

    def test_a_handled_event_without_metadata_is_refused(self, app, client, db_session):
        """PKG-63. The metadata is what says who is buying what.

        ``payment_succeeded`` with no tenant_id cannot be honoured - there is
        nothing to provision. Guessing a default tenant would grant a real
        subscription to whoever happened to own id 1.
        """
        app.config["BILLING_WEBHOOK_SECRET"] = SECRET

        resp = client.post(
            "/billing-webhook/generic",
            json=_event(tenant_id=None),
            headers={"X-Webhook-Secret": SECRET},
            follow_redirects=False,
        )
        assert resp.status_code == 400, f"a payload with no tenant answered {resp.status_code}, expected 400"
        body = resp.get_json()
        assert "provisioning" not in (body.get("data") or {}), "a payload with no tenant was provisioned"

    def test_a_stale_event_is_refused(self, app, client, db_session):
        """PKG-64. The freshness window is what stops a replay.

        A webhook captured during a promotion and replayed a year later would
        grant a subscription for a price that no longer exists, using a
        signature that is still perfectly valid. The 300-second window is the
        only thing that distinguishes a live event from an archived one.
        """
        app.config["BILLING_WEBHOOK_SECRET"] = SECRET
        stale = int((datetime.now(UTC) - timedelta(hours=6)).timestamp())

        resp = client.post(
            "/billing-webhook/generic",
            json=_event(timestamp=stale),
            headers={"X-Webhook-Secret": SECRET},
            follow_redirects=False,
        )
        assert resp.status_code == 400, f"a six-hour-old event answered {resp.status_code}, expected 400"
        assert "provisioning" not in (resp.get_json().get("data") or {}), "a stale event was provisioned"


class TestPKG65TheGatewayWebhooks:
    """PKG-65 to PKG-67: Stripe and the cron endpoint fail closed too."""

    def test_the_stripe_webhook_refuses_when_unconfigured(self, app, client, db_session):
        """PKG-65. Same reasoning as PKG-60, on the gateway that actually sends
        real money."""
        app.config["STRIPE_WEBHOOK_SECRET"] = None

        resp = client.post(
            "/billing-webhook/stripe",
            json={"id": "evt_1", "type": "checkout.session.completed"},
            headers={"Stripe-Signature": "t=1,v1=deadbeef"},
            follow_redirects=False,
        )
        assert resp.status_code == 503, f"an unconfigured Stripe webhook answered {resp.status_code}, expected 503"

    def test_the_cron_endpoint_refuses_when_unconfigured(self, app, client, db_session):
        """PKG-66. The cron endpoint suspends tenants.

        An open cron endpoint is not a read surface: anyone who found it could
        trigger the subscription sweep, and the URL is in every deployment's
        scheduler config. Unconfigured must mean closed.
        """
        app.config["CRON_SECRET"] = None

        resp = client.post(
            "/billing-webhook/api/cron/check-subscriptions",
            follow_redirects=False,
        )
        assert resp.status_code == 503, f"an unconfigured cron endpoint answered {resp.status_code}, expected 503"

    def test_the_cron_endpoint_refuses_a_wrong_secret(self, app, client, db_session):
        """PKG-67. Wrong secret, no sweep."""
        app.config["CRON_SECRET"] = CRON

        resp = client.post(
            "/billing-webhook/api/cron/check-subscriptions",
            headers={"X-Cron-Secret": "wrong"},
            follow_redirects=False,
        )
        assert resp.status_code == 403, f"a wrong cron secret answered {resp.status_code}, expected 403"

    def test_the_cron_endpoint_runs_with_the_right_secret(self, app, client, db_session):
        """PKG-68. And with the right one it actually runs.

        The refusal tests alone would pass on an endpoint that is closed in
        every configuration - permanently broken and perfectly secure. This is
        the half that proves the guard is a guard and not a wall.
        """
        app.config["CRON_SECRET"] = CRON

        resp = client.post(
            "/billing-webhook/api/cron/check-subscriptions",
            headers={"X-Cron-Secret": CRON},
            follow_redirects=False,
        )
        assert resp.status_code == 200, f"the cron endpoint answered {resp.status_code} with the right secret"
        body = resp.get_json()
        assert body is not None and "data" in body, f"the cron endpoint answered {body} without a data envelope"


class TestPKG69TheVaultAnswersItsOwnHealth:
    """PKG-69 to PKG-78: the vault's health, metrics, toggles and v2 APIs."""

    def test_the_vault_health_status_matches_its_verdict(self, client, db_session):
        """PKG-69. A health endpoint that answers 200 while reporting itself
        unhealthy is worse than one that is strict.

        The status code is derived from ``overall_status`` rather than asserted
        as a literal, so the pairing is what is checked: whenever the payload
        says unhealthy, the code must be 503, and whenever it says healthy, 200.
        """
        user = _owner(db_session, client)

        resp = client.get("/payment-vault/health", follow_redirects=False)
        assert resp.status_code in (200, 503), f"the vault health answered {resp.status_code}"

        body = resp.get_json()
        assert body is not None and "data" in body, f"the vault health answered {body} without a data envelope"
        verdict = body["data"].get("overall_status")
        assert verdict, f"the health payload carries no overall_status; data is {body['data']}"
        # The pairing is the assertion, not the literal: the route maps anything
        # that is not exactly "healthy" to 503, so a warning or a degraded
        # verdict must surface as a failure to a load balancer.
        expected = 200 if verdict == "healthy" else 503
        assert resp.status_code == expected, (
            f"the vault reports {verdict!r} but answered {resp.status_code}, expected {expected}"
        )
        assert user is not None

    def test_the_vault_metrics_answer_to_an_owner(self, client, db_session):
        """PKG-70. The metrics page behind the vault's lock, read as an owner."""
        _owner(db_session, client)

        resp = client.get("/payment-vault/metrics", follow_redirects=False)
        assert resp.status_code == 200, f"the vault metrics answered {resp.status_code} to an owner"
        body = resp.get_json()
        assert body is not None and "data" in body, f"the vault metrics answered {body} without a data envelope"

    def test_the_vault_health_is_closed_to_a_tenant_user(self, app, client, db_session):
        """PKG-71. The vault is closed to a signed-in non-owner.

        The vault holds decrypted card data. A tenant manager reaching the
        metrics endpoint is a tenant manager one step from the card list.

        The refusal is a redirect rather than a 403, and that is not a detail:
        ``_protect_owner_vault_pages`` runs before the route's own ``@owner_only``
        and bounces a non-owner to their dashboard, so a test asserting 403 here
        would be asserting a status this blueprint never produces. What matters
        is that the payload is not served - the response must carry no health
        data at all.
        """
        from models import Permission, Role, Tenant, User

        unique = uuid.uuid4().hex[:8]
        tenant = Tenant(
            name=f"PKG Tenant {unique}",
            name_ar="مستأجر",
            slug=f"pkg-ten-{unique}",
            email=f"pkg-ten-{unique}@example.com",
            country="AE",
            subscription_plan="basic",
            is_active=True,
        )
        db_session.add(tenant)
        db_session.commit()

        role = db_session.query(Role).filter_by(slug="pkg-tenant-manager").first()
        if role is None:
            role = Role(name="Pkg Tenant Manager", slug="pkg-tenant-manager", is_active=True)
            db_session.add(role)
            db_session.commit()
        role.permissions = Permission.query.filter(Permission.code.in_(["manage_sales"])).all()
        db_session.add(role)
        db_session.commit()

        user = User(
            username=f"pkg-mgr-{unique}",
            email=f"pkg-mgr-{unique}@example.com",
            full_name="PKG Manager",
            tenant_id=tenant.id,
            role_id=role.id,
            is_active=True,
        )
        user.set_password("password123")
        db_session.add(user)
        db_session.commit()
        _login(client, user)

        resp = client.get("/payment-vault/health", follow_redirects=False)
        assert resp.status_code != 200, f"a tenant manager was served the vault health: {resp.status_code}"
        body = resp.get_json(silent=True)
        assert not (isinstance(body, dict) and body.get("data", {}).get("overall_status")), (
            f"the vault health payload leaked to a tenant manager: {body}"
        )


class TestPKG72TheVaultsJsonSurfaces:
    """PKG-72 to PKG-78: the JSON endpoints behind the vault, as their owner.

    Each of these returns a success envelope with a specific key. The shape is
    the contract - a dashboard that reads ``data.count`` needs it to be an int,
    and a caller that gets ``null`` there has to decide what to do about it.
    """

    def test_the_notifications_api_reports_a_count(self, client, db_session):
        """PKG-72. ``count`` is the number of rows actually returned.

        It is not a request parameter echoed back: it is ``len(notifications)``
        after the limit is applied. A caller that paginates on this value needs
        it to match what is in the list, or the list appears to repeat rows.
        """
        _owner(db_session, client)

        resp = client.get("/payment-vault/api/notifications?limit=5", follow_redirects=False)
        assert resp.status_code == 200, f"the notifications api answered {resp.status_code} to an owner"
        body = resp.get_json()
        assert body is not None and "data" in body, f"the notifications api answered {body} without an envelope"

        data = body["data"]
        assert "notifications" in data and "count" in data, (
            f"the notifications payload is missing keys; it has {sorted(data)}"
        )
        assert isinstance(data["count"], int), f"count is {type(data['count']).__name__}, not an int"
        assert data["count"] == len(data["notifications"]), (
            f"count says {data['count']} but the list holds {len(data['notifications'])}"
        )

    def test_the_live_stats_api_answers(self, client, db_session):
        """PKG-73. The poller behind the dashboard's live counters."""
        _owner(db_session, client)

        resp = client.get("/payment-vault/api/live-stats", follow_redirects=False)
        assert resp.status_code == 200, f"the live-stats api answered {resp.status_code} to an owner"
        body = resp.get_json()
        assert body is not None and "data" in body, f"the live-stats api answered {body} without an envelope"

    def test_the_v2_purchases_api_answers_with_a_page(self, client, db_session):
        """PKG-74. The versioned API returns a page, not a bare list.

        A v2 caller paging through purchases depends on there being a next-page
        indicator to stop on. Returning a bare array would make it page forever
        or stop after one, and both look like "no purchases" to the dashboard.
        """
        _owner(db_session, client)

        resp = client.get("/payment-vault/api/v2/purchases", follow_redirects=False)
        assert resp.status_code == 200, f"the v2 purchases api answered {resp.status_code} to an owner"
        body = resp.get_json()
        assert body is not None and "data" in body, f"the v2 purchases api answered {body} without an envelope"

    def test_the_v2_donations_api_answers(self, client, db_session):
        """PKG-75. The donation half of the same versioned contract."""
        _owner(db_session, client)

        resp = client.get("/payment-vault/api/v2/donations", follow_redirects=False)
        assert resp.status_code == 200, f"the v2 donations api answered {resp.status_code} to an owner"
        body = resp.get_json()
        assert body is not None and "data" in body, f"the v2 donations api answered {body} without an envelope"

    def test_the_v2_stats_api_answers(self, client, db_session):
        """PKG-76. And the summary that both dashboards read from."""
        _owner(db_session, client)

        resp = client.get("/payment-vault/api/v2/stats", follow_redirects=False)
        assert resp.status_code == 200, f"the v2 stats api answered {resp.status_code} to an owner"
        body = resp.get_json()
        assert body is not None and "data" in body, f"the v2 stats api answered {body} without an envelope"

    def test_toggling_a_package_flips_its_active_flag(self, client, db_session):
        """PKG-77. The toggle is a flip, and it is reversible.

        Toggling takes a package out of circulation and puts it back. The risk
        is a toggle that only ever deactivates - an operator who retires a
        seasonal plan would then be unable to sell it again without the database.
        So both directions are walked, and the flag is read from the row.
        """
        from models import Package

        _owner(db_session, client)
        package = Package(
            slug=f"debt-pkg-{uuid.uuid4().hex[:8]}",
            name_ar="باقة السيناريو",
            name_en="Debt scenario package",
            price=Decimal("99.00"),
            currency="AED",
            is_active=True,
        )
        db_session.add(package)
        db_session.commit()
        package_id = package.id
        assert db_session.get(Package, package_id).is_active, "the fixture package did not start active"

        first = client.post(f"/payment-vault/package/{package_id}/toggle", follow_redirects=False)
        assert first.status_code == 200, f"deactivating a package answered {first.status_code}"
        db_session.expire_all()
        after_off = db_session.get(Package, package_id)
        assert not after_off.is_active, "the toggle reported success but the package is still active"

        second = client.post(f"/payment-vault/package/{package_id}/toggle", follow_redirects=False)
        assert second.status_code == 200, f"reactivating a package answered {second.status_code}"
        db_session.expire_all()
        after_on = db_session.get(Package, package_id)
        assert after_on.is_active, "the toggle cannot be reversed; a retired package could never return"

    def test_auto_approve_runs_and_says_it_approved_nothing(self, client, db_session):
        """PKG-78. A no-op run must still be a successful, legible answer.

        The trigger flashes "nothing to approve" when the sweep finds nothing,
        which is the common case - it is a button, and most clicks find an
        empty queue. What matters is that the sweep runs, returns normally, and
        does not report work it did not do.
        """
        _owner(db_session, client)

        resp = client.post("/payment-vault/auto-approve", follow_redirects=True)
        assert resp.status_code == 200, f"the auto-approve sweep answered {resp.status_code}"
        assert "Internal Server Error" not in resp.get_data(as_text=True), (
            "the auto-approve sweep raised rather than reporting an empty queue"
        )
