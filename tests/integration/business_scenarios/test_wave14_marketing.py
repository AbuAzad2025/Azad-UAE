"""Wave 14 - email marketing and gamification. Prefix MKT.

These two blueprints share a prefix because they share a failure mode: both
hand something to a person who is not the operator. A campaign hands a message
to a subscriber, and points hand a badge to an employee. In both cases the
thing that must not happen is the operator reaching somebody else's audience:
a list that belongs to another tenant, a campaign that sends to another
tenant's subscribers, a leaderboard that shows another tenant's staff.

The email side has one rule that the service is strict about, and it is the
reason this blueprint is in the catalogue at all. Sending is not idempotent by
accident: a campaign starts as a draft, and a campaign that has been sent
cannot be sent again (MKT-15). A campaign that can be sent twice sends its
audience twice, and an email to a customer is not a thing you can take back.

The gamification side is a points economy, and its rules are small but exact.
The points for an action are configured server-side, not taken from the
caller (MKT-17), an unknown action is worth nothing rather than everything
(MKT-18), and a badge follows the points, not the other way round (MKT-19).
Awarding points is the one route on the blueprint that needs the ``admin``
permission, because it is the only one that changes somebody else's standing
(MKT-05).
"""

from __future__ import annotations

import uuid

import pytest

MARKETING_VIEW_PATHS = [
    "/marketing/",
    "/marketing/lists",
    "/marketing/templates",
    "/marketing/campaigns/1",
]
MARKETING_POST_PATHS = [
    "/marketing/campaigns/create",
    "/marketing/campaigns/1/send",
    "/marketing/lists/create",
    "/marketing/templates/create",
]
GAMIFICATION_VIEW_PATHS = [
    "/gamification/leaderboard",
    "/gamification/my-stats",
]


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="mkt-user", permissions=(), branch=None):
    from models import Permission, User

    role = _role(db_session, slug)
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"mkt-{slug}-{unique}",
        email=f"mkt-{unique}@example.com",
        full_name=f"MKT {slug}",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    # /auth/login refuses to switch users while a session is open, so a scenario
    # that needs two actors signs the first one out first.
    client.get("/auth/logout", follow_redirects=True)
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": "Str0ng!Pass99"},
        follow_redirects=True,
    )


def _with(client, db_session, tenant, branch, codes, slug):
    """A signed-in user carrying exactly ``codes``.

    The slug carries the permission set, because _role() reuses a role by slug
    and *replaces* its permissions on every call: two scenarios asking for
    different grants under one shared slug would overwrite each other.
    """
    slug = slug + "-" + "-".join(c.replace(".", "-") for c in codes)
    user = _user(db_session, tenant, slug=slug, permissions=list(codes), branch=branch)
    _login(client, user)
    return user


def _email_list(db_session, tenant, *, name="Probe List"):
    from models import EmailList

    email_list = EmailList(
        tenant_id=tenant.id,
        name=f"{name}-{uuid.uuid4().hex[:4]}",
        is_active=True,
    )
    db_session.add(email_list)
    db_session.commit()
    return email_list


def _subscriber(db_session, tenant, email_list, *, status="subscribed"):
    from models import EmailSubscriber

    subscriber = EmailSubscriber(
        tenant_id=tenant.id,
        list_id=email_list.id,
        email=f"sub-{uuid.uuid4().hex[:8]}@example.com",
        name="Probe Subscriber",
        status=status,
    )
    db_session.add(subscriber)
    db_session.commit()
    return subscriber


def _template(db_session, tenant, *, name="Probe Template"):
    from models import EmailTemplate

    template = EmailTemplate(
        tenant_id=tenant.id,
        name=f"{name}-{uuid.uuid4().hex[:4]}",
        subject="Your monthly statement",
        body_html="<p>Hello</p>",
        from_email="noreply@example.com",
        is_active=True,
    )
    db_session.add(template)
    db_session.commit()
    return template


def _campaign(db_session, tenant, *, name="Probe Campaign", email_list=None, template=None, status="draft"):
    from models import EmailCampaign

    campaign = EmailCampaign(
        tenant_id=tenant.id,
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        list_id=email_list.id if email_list else None,
        template_id=template.id if template else None,
        status=status,
        is_active=True,
    )
    db_session.add(campaign)
    db_session.commit()
    return campaign


def _other_tenant(db_session):
    """A second tenant, for the isolation assertions."""
    from models import Tenant

    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f"Other Tenant {unique}",
        name_ar="شركة أخرى",
        slug=f"other-tenant-{unique}",
        email=f"other-{unique}@example.com",
        country="AE",
        subscription_plan="basic",
    )
    db_session.add(tenant)
    db_session.commit()
    return tenant


@pytest.fixture
def mail_service(app):
    """A working - and silenced - mail extension.

    The application only initialises Flask-Mail when MAIL_USERNAME is
    configured, so without this the campaign send path finds no mail service
    and refuses before it has sent anything. Initialising the extension here
    lets the send path be exercised for real: MAIL_SUPPRESS_SEND is on in
    testing, so no message leaves the machine.
    """
    from extensions import mail

    mail.init_app(app)
    return app.extensions["mail"]


class TestMKT01ThePermissionBoundary:
    """MKT-01 to MKT-05: who may reach the marketing surface."""

    def test_anonymous_is_refused_everywhere(self, client):
        """MKT-01."""
        for path in MARKETING_VIEW_PATHS + GAMIFICATION_VIEW_PATHS:
            resp = client.get(path)
            assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code}"
        for path in MARKETING_POST_PATHS:
            resp = client.post(path, data={})
            assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code}"

    def test_the_marketing_permissions_are_seeded(self, db_session):
        """MKT-02."""
        from models import Permission

        for code in ("marketing.manage", "admin", "view_reports"):
            assert db_session.query(Permission).filter_by(code=code).first() is not None, f"{code} is not seeded"

    def test_marketing_manage_reaches_the_campaign_surface(self, client, db_session, demo_tenant, demo_branch):
        """MKT-03."""
        _with(client, db_session, demo_tenant, demo_branch, ["marketing.manage"], "marketer")
        assert client.get("/marketing/").status_code == 200
        assert client.get("/marketing/lists").status_code == 200
        assert client.get("/marketing/templates").status_code == 200

    def test_view_reports_does_not_reach_the_marketing_surface(self, client, db_session, demo_tenant, demo_branch):
        """MKT-04. Reading reports is not the authority to send mail."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/marketing/").status_code == 403
        assert client.get("/marketing/lists").status_code == 403

    def test_awarding_points_needs_the_admin_permission(self, client, db_session, demo_tenant, demo_branch):
        """MKT-05. It is the only route that changes somebody else's standing."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/gamification/award/sale_created").status_code == 403

        _with(client, db_session, demo_tenant, demo_branch, ["admin"], "admin")
        resp = client.get("/gamification/award/sale_created")
        assert resp.status_code == 200


class TestMKT12ListsAndTemplates:
    """MKT-06 to MKT-10: the audience and the message."""

    def test_a_list_is_created(self, client, db_session, demo_tenant, demo_branch):
        """MKT-06."""
        _with(client, db_session, demo_tenant, demo_branch, ["marketing.manage"], "marketer")
        name = f"Customers {uuid.uuid4().hex[:4]}"
        resp = client.post("/marketing/lists/create", data={"name": name})
        assert resp.status_code in (200, 302)

        from models import EmailList

        created = db_session.query(EmailList).filter_by(tenant_id=demo_tenant.id, name=name).first()
        assert created is not None, "the list was not created"

    def test_a_list_without_a_name_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """MKT-07. A nameless list is an audience nobody can be shown."""
        _with(client, db_session, demo_tenant, demo_branch, ["marketing.manage"], "marketer")
        resp = client.post("/marketing/lists/create", data={"description": "no name here"})
        assert resp.status_code in (200, 302)

        from models import EmailList

        assert db_session.query(EmailList).filter_by(tenant_id=demo_tenant.id).count() == 0

    def test_a_template_is_created(self, client, db_session, demo_tenant, demo_branch):
        """MKT-08."""
        _with(client, db_session, demo_tenant, demo_branch, ["marketing.manage"], "marketer")
        name = f"Statement {uuid.uuid4().hex[:4]}"
        resp = client.post(
            "/marketing/templates/create",
            data={
                "name": name,
                "subject": "Your statement",
                "body_html": "<p>Hello</p>",
                "from_email": "noreply@example.com",
            },
        )
        assert resp.status_code in (200, 302)

        from models import EmailTemplate

        created = db_session.query(EmailTemplate).filter_by(tenant_id=demo_tenant.id, name=name).first()
        assert created is not None, "the template was not created"
        assert created.subject == "Your statement"

    def test_a_template_without_a_subject_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """MKT-09. A message with no subject is not a message."""
        _with(client, db_session, demo_tenant, demo_branch, ["marketing.manage"], "marketer")
        resp = client.post(
            "/marketing/templates/create",
            data={"name": "No subject", "body_html": "<p>Hello</p>"},
        )
        assert resp.status_code in (200, 302)

        from models import EmailTemplate

        assert db_session.query(EmailTemplate).filter_by(tenant_id=demo_tenant.id).count() == 0

    def test_the_lists_page_shows_only_our_own_lists(self, client, db_session, demo_tenant, demo_branch):
        """MKT-10. Another tenant's audience is not an audience we may use."""
        other = _other_tenant(db_session)
        foreign_list = _email_list(db_session, other, name="Foreign List")

        _with(client, db_session, demo_tenant, demo_branch, ["marketing.manage"], "marketer")
        resp = client.get("/marketing/lists")
        assert resp.status_code == 200
        assert foreign_list.name not in resp.get_data(as_text=True)


class TestMKT18Campaigns:
    """MKT-11 to MKT-16: the campaign and the one time it may be sent."""

    def test_a_campaign_is_created_as_a_draft(self, client, db_session, demo_tenant, demo_branch):
        """MKT-11."""
        _with(client, db_session, demo_tenant, demo_branch, ["marketing.manage"], "marketer")
        name = f"October {uuid.uuid4().hex[:4]}"
        resp = client.post("/marketing/campaigns/create", data={"name": name})
        assert resp.status_code in (200, 302)

        from models import EmailCampaign

        campaign = db_session.query(EmailCampaign).filter_by(tenant_id=demo_tenant.id, name=name).first()
        assert campaign is not None, "the campaign was not created"
        assert campaign.status == "draft", "a new campaign must not be sent before it is asked for"

    def test_a_campaign_without_a_name_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """MKT-12."""
        _with(client, db_session, demo_tenant, demo_branch, ["marketing.manage"], "marketer")
        resp = client.post("/marketing/campaigns/create", data={"status": "draft"})
        assert resp.status_code in (200, 302)

        from models import EmailCampaign

        assert db_session.query(EmailCampaign).filter_by(tenant_id=demo_tenant.id).count() == 0

    def test_a_campaign_is_sent_to_the_subscribers_of_its_list(
        self, client, db_session, demo_tenant, demo_branch, mail_service
    ):
        """MKT-13."""
        email_list = _email_list(db_session, demo_tenant)
        _subscriber(db_session, demo_tenant, email_list)
        template = _template(db_session, demo_tenant)
        campaign = _campaign(db_session, demo_tenant, email_list=email_list, template=template)

        _with(client, db_session, demo_tenant, demo_branch, ["marketing.manage"], "marketer")
        resp = client.post(f"/marketing/campaigns/{campaign.id}/send")
        assert resp.status_code in (200, 302)

        db_session.expire_all()
        from models import CampaignLog, EmailCampaign

        sent = db_session.query(EmailCampaign).get(campaign.id)
        assert sent.status == "sent"
        assert sent.sent_count == 1
        assert db_session.query(CampaignLog).filter_by(campaign_id=campaign.id, status="sent").count() == 1

    def test_a_campaign_with_no_subscribers_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """MKT-14. A campaign to nobody is not a campaign."""
        email_list = _email_list(db_session, demo_tenant)
        template = _template(db_session, demo_tenant)
        campaign = _campaign(db_session, demo_tenant, email_list=email_list, template=template)

        _with(client, db_session, demo_tenant, demo_branch, ["marketing.manage"], "marketer")
        resp = client.post(f"/marketing/campaigns/{campaign.id}/send")
        assert resp.status_code in (200, 302)

        db_session.expire_all()
        from models import EmailCampaign

        assert db_session.query(EmailCampaign).get(campaign.id).status == "draft", (
            "a campaign with no subscribers was marked as sent"
        )

    def test_a_campaign_cannot_be_sent_twice(self, client, db_session, demo_tenant, demo_branch, mail_service):
        """MKT-15. An email to a customer is not a thing you can take back."""
        email_list = _email_list(db_session, demo_tenant)
        _subscriber(db_session, demo_tenant, email_list)
        template = _template(db_session, demo_tenant)
        campaign = _campaign(db_session, demo_tenant, email_list=email_list, template=template)

        _with(client, db_session, demo_tenant, demo_branch, ["marketing.manage"], "marketer")
        client.post(f"/marketing/campaigns/{campaign.id}/send")
        resp = client.post(f"/marketing/campaigns/{campaign.id}/send")
        assert resp.status_code in (200, 302)

        db_session.expire_all()
        from models import CampaignLog, EmailCampaign

        assert db_session.query(EmailCampaign).get(campaign.id).status == "sent"
        assert db_session.query(CampaignLog).filter_by(campaign_id=campaign.id).count() == 1, (
            "the campaign went out twice"
        )

    def test_another_tenants_campaign_is_not_reachable(self, client, db_session, demo_tenant, demo_branch):
        """MKT-16."""
        other = _other_tenant(db_session)
        foreign = _campaign(db_session, other, name="Foreign Campaign")

        _with(client, db_session, demo_tenant, demo_branch, ["marketing.manage"], "marketer")
        resp = client.get(f"/marketing/campaigns/{foreign.id}")
        assert resp.status_code in (302, 404), f"the cross-tenant read answered {resp.status_code}"
        assert foreign.name not in resp.get_data(as_text=True)

        resp = client.post(f"/marketing/campaigns/{foreign.id}/send")
        assert resp.status_code in (302, 404), f"the cross-tenant send answered {resp.status_code}"

        db_session.expire_all()
        from models import EmailCampaign

        assert db_session.query(EmailCampaign).get(foreign.id).status == "draft"


class TestMKT24PointsAndBadges:
    """MKT-17 to MKT-22: the points economy."""

    def test_awarding_points_reports_the_configured_value(self, client, db_session, demo_tenant, demo_branch):
        """MKT-17. The points for an action are the server's, not the caller's."""
        from services.gamification_service import GamificationService

        _with(client, db_session, demo_tenant, demo_branch, ["admin"], "admin")
        resp = client.get("/gamification/award/sale_created")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["success"] is True
        assert data["points_awarded"] == GamificationService.POINTS_CONFIG["sale_created"]

    def test_an_unknown_action_is_worth_nothing(self, client, db_session, demo_tenant, demo_branch):
        """MKT-18. An action the economy does not know is not a bonus."""
        _with(client, db_session, demo_tenant, demo_branch, ["admin"], "admin")
        resp = client.get("/gamification/award/not-a-real-action")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["points_awarded"] == 0

    def test_the_badge_follows_the_points(self, client, db_session, demo_tenant, demo_branch):
        """MKT-19. The badge is a function of the points, not a separate award."""
        from services.gamification_service import GamificationService

        assert GamificationService.get_user_badge(0)["key"] == "newbie"
        assert GamificationService.get_user_badge(100)["key"] == "bronze"
        assert GamificationService.get_user_badge(5000)["key"] == "platinum"

    def test_the_leaderboard_answers(self, client, db_session, demo_tenant, demo_branch):
        """MKT-20."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/gamification/leaderboard")
        assert resp.status_code == 200
        assert "leaderboard" in resp.get_data(as_text=True)

    def test_my_stats_answers_for_the_caller(self, client, db_session, demo_tenant, demo_branch):
        """MKT-21. Somebody's own statistics are about themselves."""
        user = _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        resp = client.get("/gamification/my-stats")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["success"] is True
        assert data["points"] == 0
        assert user.id is not None

    def test_the_scenario_covers_every_marketing_route(self, app):
        """MKT-22. A scenario that stops covering a route stops being a scenario."""
        known = {
            "/marketing/",
            "/marketing/campaigns/create",
            "/marketing/campaigns/<int:campaign_id>",
            "/marketing/campaigns/<int:campaign_id>/send",
            "/marketing/lists",
            "/marketing/lists/create",
            "/marketing/templates",
            "/marketing/templates/create",
            "/gamification/leaderboard",
            "/gamification/my-stats",
            "/gamification/award/<action>",
        }
        live = {
            rule.rule
            for rule in app.url_map.iter_rules()
            if rule.rule.startswith("/marketing") or rule.rule.startswith("/gamification")
        }
        assert live == known, f"the marketing route inventory moved: {sorted(live ^ known)}"


class TestMKT30TheStructure:
    """MKT-23 to MKT-24: what the tables have to carry."""

    def test_every_marketing_model_carries_a_tenant_id(self, db_session):
        """MKT-23. An audience without a tenant is an audience nobody owns."""
        from models.email_marketing import (
            CampaignLog,
            EmailCampaign,
            EmailList,
            EmailSubscriber,
            EmailTemplate,
        )

        for model in (EmailCampaign, EmailList, EmailSubscriber, EmailTemplate, CampaignLog):
            column = model.__table__.columns.get("tenant_id")
            assert column is not None, f"{model.__name__} has no tenant_id"
            assert column.nullable is False, f"{model.__name__}.tenant_id is nullable"

    def test_a_campaign_carries_its_counts_as_integers(self, db_session):
        """MKT-24. A count is a count, not a decimal."""
        from sqlalchemy import Integer

        from models.email_marketing import EmailCampaign

        for name in ("sent_count", "open_count", "click_count", "bounce_count"):
            column = EmailCampaign.__table__.columns.get(name)
            assert column is not None, f"EmailCampaign.{name} does not exist"
            assert isinstance(column.type, Integer), f"EmailCampaign.{name} is {column.type}, not an integer"
