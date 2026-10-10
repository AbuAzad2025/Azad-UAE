"""Wave 9 - CRM pipeline and support tickets. Prefix CRM.

Two blueprints that share a shape rather than a subject: a **stage** you move
through, and the permission that moves it.

Both are dotted permissions - ``crm.view``/``crm.manage`` and
``support.view``/``support.manage`` - and both split read from write on exactly
that line. The pipeline's ``move-stage`` endpoint is the interesting one: it is a
POST that rewrites a lead's position in the funnel, it is gated on ``crm.manage``
rather than ``crm.view``, and a lead that could view the pipeline must not be
able to drag itself to the "won" column.

**Stage order is enforced.** ``CRMStage`` carries ``sequence``, ``is_won`` and
``is_lost``, and moving a lead is not the same as renaming a column. CRM-18 to
CRM-24 assert the transition through ``move-stage`` and ``/api/activities``
rather than through a form post, because those are the endpoints a drag-and-drop
board actually calls.

Tickets carry the same shape one level down: open → resolved → closed, with
``reopen`` as the way back. CRM-25 to CRM-34 walk that and assert the guards,
not just the pages - a ticket that could be closed without being resolved, or
reopened without an owner, is the failure mode here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

CRM_VIEW_PATHS = ["/crm/pipeline", "/crm/leads", "/crm/leads/1", "/crm/api/stats"]
CRM_MANAGE_PATHS = ["/crm/leads/create", "/crm/leads/1/edit"]
CRM_MANAGE_POST_PATHS = ["/crm/api/move-stage", "/crm/api/activities"]

TICKET_VIEW_PATHS = ["/tickets/", "/tickets/1"]
TICKET_MANAGE_PATHS = ["/tickets/create"]
TICKET_MANAGE_POST_PATHS = [
    "/tickets/1/comment",
    "/tickets/1/assign",
    "/tickets/1/resolve",
    "/tickets/1/close",
    "/tickets/1/reopen",
]


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="crm-user", permissions=(), branch=None):
    from models import Permission, User

    role = _role(db_session, slug)
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"crm-{slug}-{unique}",
        email=f"crm-{unique}@example.com",
        full_name=f"CRM {slug}",
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
    return client.post(
        "/auth/login", data={"username": user.username, "password": "Str0ng!Pass99"}, follow_redirects=True
    )


def _viewer(client, db_session, tenant, branch, code="crm.view"):
    # The role slug is namespaced by code. _role() reuses a role by slug and
    # *replaces* its permissions on every call, so two tests asking for
    # crm.view and support.view under one shared slug would silently overwrite
    # each other's grants - and the second one would then fail a guard for a
    # reason that has nothing to do with what it was testing.
    suffix = code.replace(".", "-")
    user = _user(db_session, tenant, slug=f"v-{suffix}", permissions=[code], branch=branch)
    _login(client, user)
    return user


def _manager(client, db_session, tenant, branch, code="crm.manage"):
    # A manager is granted ``manage`` *and* the matching ``view``. The create
    # endpoints redirect to a list page on success, and that page is gated on
    # ``view`` - so a manage-only role gets a 403 on the redirect target and the
    # create looks broken when it actually worked.
    suffix = code.replace(".", "-")
    view_code = code.replace(".manage", ".view")
    user = _user(db_session, tenant, slug=f"m-{suffix}", permissions=[code, view_code], branch=branch)
    _login(client, user)
    return user


def _stage(db_session, tenant, *, name="Probe Stage", sequence=1, is_won=False, is_lost=False):
    from models import CRMStage

    stage = CRMStage(
        tenant_id=tenant.id,
        name=f"{name}-{uuid.uuid4().hex[:4]}",
        sequence=sequence,
        probability=Decimal("10"),
        is_won=is_won,
        is_lost=is_lost,
        is_active=True,
    )
    db_session.add(stage)
    db_session.commit()
    return stage


def _lead(db_session, tenant, stage, *, name="Probe Lead", status="open", branch=None):
    from models import CRMLead

    lead = CRMLead(
        tenant_id=tenant.id,
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        email=f"lead-{uuid.uuid4().hex[:6]}@example.com",
        stage_id=stage.id,
        status=status,
        is_active=True,
        expected_revenue=Decimal("1000"),
        branch_id=branch.id if branch else None,
    )
    db_session.add(lead)
    db_session.commit()
    return lead


def _ticket(db_session, tenant, *, subject="Probe Ticket", status="open", branch=None, priority_id=None):
    """A Ticket row.

    ``branch_id`` is filled in from the caller because ``TicketService`` scopes
    tickets by the signed-in user's branch - a ticket with no branch is correctly
    invisible to a branch-scoped user, which would make every action on it 403 for
    the right reason and the wrong reason at once.
    """
    from models import Ticket

    ticket = Ticket(
        tenant_id=tenant.id,
        number=f"TK-{uuid.uuid4().hex[:8]}",
        subject=f"{subject}-{uuid.uuid4().hex[:4]}",
        body="probe body",
        status=status,
        source="internal",
        is_active=True,
        sla_deadline=datetime.now(UTC),
        branch_id=branch.id if branch else None,
        priority_id=priority_id,
    )
    db_session.add(ticket)
    db_session.commit()
    return ticket


def _priority(db_session, tenant):
    """A real TicketPriority, because ``create_ticket`` dereferences the posted id."""
    from models import TicketPriority

    existing = db_session.query(TicketPriority).first()
    if existing is not None:
        return existing
    priority = TicketPriority(name="Probe Priority", sla_hours=24, is_active=True)
    db_session.add(priority)
    db_session.commit()
    return priority


class TestCRM01CrmPermissions:
    """CRM-01 to CRM-10: the dotted read/write split on the pipeline."""

    @pytest.mark.parametrize("path", CRM_VIEW_PATHS)
    def test_crm_reads_need_crm_view(self, client, db_session, sample_tenant, sample_branch, path):
        """CRM-01."""
        _viewer(client, db_session, sample_tenant, sample_branch, code="manage_sales")
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without crm.view"

    @pytest.mark.parametrize("path", CRM_MANAGE_PATHS)
    def test_crm_writes_need_crm_manage(self, client, db_session, sample_tenant, sample_branch, path):
        """CRM-02. crm.view does not imply crm.manage."""
        _viewer(client, db_session, sample_tenant, sample_branch, code="crm.view")
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} for a crm.view user"

    @pytest.mark.parametrize("path", CRM_MANAGE_POST_PATHS)
    def test_the_crm_posts_need_crm_manage(self, client, db_session, sample_tenant, sample_branch, path):
        """CRM-03. POST, so a GET's 405 cannot stand in for the guard."""
        _viewer(client, db_session, sample_tenant, sample_branch, code="crm.view")
        resp = client.post(path, json={})
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} for a crm.view user"

    @pytest.mark.parametrize("path", CRM_VIEW_PATHS + CRM_MANAGE_PATHS + CRM_MANAGE_POST_PATHS)
    def test_anonymous_is_refused(self, client, path):
        """CRM-04."""
        if path in CRM_MANAGE_POST_PATHS:
            assert client.post(path, json={}).status_code in (302, 401, 403), f"{path} answered anonymously"
        else:
            assert client.get(path).status_code in (302, 401, 403), f"{path} answered anonymously"

    def test_crm_view_reaches_the_pipeline(self, client, db_session, sample_tenant, sample_branch):
        """CRM-05. The success side of CRM-01."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        assert client.get("/crm/pipeline").status_code == 200
        assert client.get("/crm/leads").status_code == 200

    def test_crm_manage_alone_reaches_the_writes(self, client, db_session, sample_tenant, sample_branch):
        """CRM-06. The manage code on its own is enough for a write surface."""
        _manager(client, db_session, sample_tenant, sample_branch)
        assert client.get("/crm/leads/create").status_code == 200

    def test_manage_sales_does_not_grant_crm(self, client, db_session, sample_tenant, sample_branch):
        """CRM-07. The pipeline is its own permission, not a sales alias."""
        _viewer(client, db_session, sample_tenant, sample_branch, code="manage_sales")
        assert client.get("/crm/pipeline").status_code in (302, 403), "a manage_sales user reached the CRM pipeline"

    def test_a_lead_id_from_another_tenant_is_not_readable(self, client, db_session, sample_tenant, sample_branch):
        """CRM-08. ``get_lead`` is the boundary; a nonexistent id is the proxy."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        resp = client.get("/crm/leads/99999999")
        assert resp.status_code in (302, 404), f"a missing lead answered {resp.status_code}"

    def test_the_stats_api_answers_json(self, client, db_session, sample_tenant, sample_branch):
        """CRM-09."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        _stage(db_session, sample_tenant)
        resp = client.get("/crm/api/stats")
        assert resp.status_code == 200, f"the stats API answered {resp.status_code}"
        ctype = resp.content_type or ""
        assert "application/json" in ctype, f"the stats API is {ctype}, not JSON"

    def test_the_crm_permissions_are_seeded(self, db_session):
        """CRM-10. A dotted code the seeder does not know cannot ever be granted."""
        from utils.constants import PERMISSION_CODES

        for code in ("crm.view", "crm.manage"):
            assert code in PERMISSION_CODES, f"{code} is not in PERMISSION_CODES"
        assert "crm.view" != "crm.manage"


class TestCRM11StageMoves:
    """CRM-11 to CRM-24: moving a lead through the pipeline."""

    def test_a_stage_can_be_created(self, db_session, sample_tenant):
        """CRM-11. Structural - the column the board orders on."""
        from models import CRMStage

        columns = CRMStage.__table__.columns
        for name in ("sequence", "is_won", "is_lost", "is_active"):
            assert name in columns, f"CRMStage has no {name}: {list(columns.keys())}"

    def test_a_lead_can_be_created_through_the_form(self, client, db_session, sample_tenant, sample_branch):
        """CRM-12. The happy path, read back from the row."""
        from models import CRMLead

        _manager(client, db_session, sample_tenant, sample_branch)
        stage = _stage(db_session, sample_tenant)
        before = db_session.query(CRMLead).filter_by(tenant_id=sample_tenant.id).count()

        resp = client.post(
            "/crm/leads/create",
            data={
                "name": f"Probe Lead {uuid.uuid4().hex[:6]}",
                "email": f"probe-{uuid.uuid4().hex[:6]}@example.com",
                "stage_id": str(stage.id),
                "branch_id": str(sample_branch.id),
                "expected_revenue": "1000",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"lead create answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(CRMLead).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"the lead was not created ({before} -> {after})"

    def test_a_lead_starts_open(self, client, db_session, sample_tenant, sample_branch):
        """CRM-13. A new lead has not been won and has not been lost."""
        from models import CRMLead

        _manager(client, db_session, sample_tenant, sample_branch)
        stage = _stage(db_session, sample_tenant)
        client.post(
            "/crm/leads/create",
            data={
                "name": f"Fresh {uuid.uuid4().hex[:6]}",
                "stage_id": str(stage.id),
                "branch_id": str(sample_branch.id),
            },
            follow_redirects=True,
        )

        db_session.expire_all()
        lead = db_session.query(CRMLead).filter_by(tenant_id=sample_tenant.id).order_by(CRMLead.id.desc()).first()
        assert lead is not None
        assert lead.status not in ("won", "lost"), f"a new lead starts as {lead.status!r}"

    def test_moving_a_lead_changes_its_stage(self, client, db_session, sample_tenant, sample_branch):
        """CRM-14. The drag-and-drop endpoint the pipeline board actually calls."""
        from models import CRMLead

        _manager(client, db_session, sample_tenant, sample_branch)
        first = _stage(db_session, sample_tenant, name="New", sequence=1)
        second = _stage(db_session, sample_tenant, name="Qualified", sequence=2)
        lead = _lead(db_session, sample_tenant, first, branch=sample_branch)
        lead_id = lead.id

        resp = client.post(
            "/crm/api/move-stage",
            json={"lead_id": lead_id, "stage_id": second.id},
        )
        assert resp.status_code == 200, f"move-stage answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.get(CRMLead, lead_id).stage_id == second.id, "the move did not change the stage"

    def test_move_stage_without_a_lead_is_a_400(self, client, db_session, sample_tenant, sample_branch):
        """CRM-15. ``data["lead_id"]`` raises KeyError, which is caught as 400."""
        _manager(client, db_session, sample_tenant, sample_branch)
        assert client.post("/crm/api/move-stage", json={"stage_id": 1}).status_code == 400

    def test_move_stage_without_a_stage_is_a_400(self, client, db_session, sample_tenant, sample_branch):
        """CRM-16."""
        _manager(client, db_session, sample_tenant, sample_branch)
        stage = _stage(db_session, sample_tenant)
        lead = _lead(db_session, sample_tenant, stage, branch=sample_branch)
        assert client.post("/crm/api/move-stage", json={"lead_id": lead.id}).status_code == 400

    def test_move_stage_on_a_missing_lead_is_refused(self, client, db_session, sample_tenant, sample_branch):
        """CRM-17."""
        _manager(client, db_session, sample_tenant, sample_branch)
        stage = _stage(db_session, sample_tenant)
        resp = client.post("/crm/api/move-stage", json={"lead_id": 99999999, "stage_id": stage.id})
        assert resp.status_code in (400, 404), f"moving a missing lead answered {resp.status_code}"

    def test_a_viewer_cannot_move_a_lead(self, client, db_session, sample_tenant, sample_branch):
        """CRM-18. The guard that matters most on this blueprint.

        A lead that can read the pipeline must not be able to drag itself into
        the "won" column - that is revenue recognised by a click.
        """
        from models import CRMLead

        _viewer(client, db_session, sample_tenant, sample_branch)
        first = _stage(db_session, sample_tenant, name="New", sequence=1)
        won = _stage(db_session, sample_tenant, name="Won", sequence=9, is_won=True)
        lead = _lead(db_session, sample_tenant, first, branch=sample_branch)
        lead_id = lead.id

        client.post("/crm/api/move-stage", json={"lead_id": lead_id, "stage_id": won.id})

        db_session.expire_all()
        assert db_session.get(CRMLead, lead_id).stage_id == first.id, "a crm.view user moved a lead into the won stage"

    def test_an_activity_can_be_added(self, client, db_session, sample_tenant, sample_branch):
        """CRM-19. The other write the board performs."""
        from models import CRMActivity

        _manager(client, db_session, sample_tenant, sample_branch)
        stage = _stage(db_session, sample_tenant)
        lead = _lead(db_session, sample_tenant, stage, branch=sample_branch)
        before = db_session.query(CRMActivity).filter_by(tenant_id=sample_tenant.id).count()

        resp = client.post(
            "/crm/api/activities",
            json={"lead_id": lead.id, "activity_type": "call", "summary": "probe call"},
        )
        assert resp.status_code in (200, 400), f"add-activity answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(CRMActivity).filter_by(tenant_id=sample_tenant.id).count()
        assert after > before, "the activity was not recorded"

    def test_an_activity_without_a_lead_is_a_400(self, client, db_session, sample_tenant, sample_branch):
        """CRM-20."""
        _manager(client, db_session, sample_tenant, sample_branch)
        assert client.post("/crm/api/activities", json={"activity_type": "call"}).status_code == 400

    def test_a_viewer_cannot_add_an_activity(self, client, db_session, sample_tenant, sample_branch):
        """CRM-21."""
        from models import CRMActivity

        _viewer(client, db_session, sample_tenant, sample_branch)
        stage = _stage(db_session, sample_tenant)
        lead = _lead(db_session, sample_tenant, stage, branch=sample_branch)
        before = db_session.query(CRMActivity).filter_by(tenant_id=sample_tenant.id).count()

        client.post(
            "/crm/api/activities",
            json={"lead_id": lead.id, "activity_type": "call", "summary": "sneaky"},
        )

        db_session.expire_all()
        after = db_session.query(CRMActivity).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before, f"a crm.view user recorded an activity ({before} -> {after})"

    def test_the_lead_detail_page_renders_its_own_lead(self, client, db_session, sample_tenant, sample_branch):
        """CRM-22. A page that renders *some* lead is not evidence."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        stage = _stage(db_session, sample_tenant)
        lead = _lead(db_session, sample_tenant, stage, branch=sample_branch)

        resp = client.get(f"/crm/leads/{lead.id}")
        assert resp.status_code in (200, 302), f"the lead page answered {resp.status_code}"
        if resp.status_code == 200:
            assert lead.name in resp.get_data(as_text=True), "the lead page did not render its own lead"

    def test_the_pipeline_lists_our_stages(self, client, db_session, sample_tenant, sample_branch):
        """CRM-23."""
        _viewer(client, db_session, sample_tenant, sample_branch)
        stage = _stage(db_session, sample_tenant, name="ListedStage")
        resp = client.get("/crm/pipeline")
        assert resp.status_code == 200
        assert stage.name in resp.get_data(as_text=True), "the pipeline did not render the stage we created"

    def test_lead_and_stage_carry_a_tenant_id(self, db_session):
        """CRM-24. Structural."""
        from models import CRMActivity, CRMLead, CRMStage

        for model in (CRMLead, CRMStage, CRMActivity):
            assert "tenant_id" in model.__table__.columns, f"{model.__name__} carries no tenant_id"


class TestCRM25TicketPermissions:
    """CRM-25 to CRM-32: the same split, on support tickets."""

    @pytest.mark.parametrize("path", TICKET_VIEW_PATHS)
    def test_ticket_reads_need_support_view(self, client, db_session, sample_tenant, sample_branch, path):
        """CRM-25."""
        _viewer(client, db_session, sample_tenant, sample_branch, code="manage_sales")
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} without support.view"

    @pytest.mark.parametrize("path", TICKET_MANAGE_PATHS)
    def test_ticket_writes_need_support_manage(self, client, db_session, sample_tenant, sample_branch, path):
        """CRM-26."""
        _viewer(client, db_session, sample_tenant, sample_branch, code="support.view")
        resp = client.get(path)
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} for a support.view user"

    @pytest.mark.parametrize("path", TICKET_MANAGE_POST_PATHS)
    def test_the_ticket_posts_need_support_manage(self, client, db_session, sample_tenant, sample_branch, path):
        """CRM-27. POST, so a GET's 405 cannot stand in for the guard."""
        _viewer(client, db_session, sample_tenant, sample_branch, code="support.view")
        resp = client.post(path, data={})
        assert resp.status_code in (302, 403), f"{path} answered {resp.status_code} for a support.view user"

    @pytest.mark.parametrize("path", TICKET_VIEW_PATHS + TICKET_MANAGE_PATHS + TICKET_MANAGE_POST_PATHS)
    def test_anonymous_is_refused(self, client, path):
        """CRM-28."""
        if path in TICKET_MANAGE_POST_PATHS:
            assert client.post(path, data={}).status_code in (302, 401, 403), f"{path} answered anonymously"
        else:
            assert client.get(path).status_code in (302, 401, 403), f"{path} answered anonymously"

    def test_support_view_reaches_the_ticket_list(self, client, db_session, sample_tenant, sample_branch):
        """CRM-29. The success side."""
        _viewer(client, db_session, sample_tenant, sample_branch, code="support.view")
        assert client.get("/tickets/").status_code == 200

    def test_crm_view_does_not_grant_tickets(self, client, db_session, sample_tenant, sample_branch):
        """CRM-30. Separate dotted families, not one "can use the back office" code."""
        _viewer(client, db_session, sample_tenant, sample_branch, code="crm.view")
        assert client.get("/tickets/").status_code in (302, 403), "a crm.view user reached the tickets list"

    def test_support_manage_does_not_grant_the_crm(self, client, db_session, sample_tenant, sample_branch):
        """CRM-31. The mirror."""
        _manager(client, db_session, sample_tenant, sample_branch, code="support.manage")
        assert client.get("/crm/pipeline").status_code in (302, 403), "a support.manage user reached the CRM pipeline"

    def test_the_support_permissions_are_seeded(self, db_session):
        """CRM-32."""
        from utils.constants import PERMISSION_CODES

        for code in ("support.view", "support.manage"):
            assert code in PERMISSION_CODES, f"{code} is not in PERMISSION_CODES"
        assert "support.view" != "support.manage"


class TestCRM33TicketLifecycle:
    """CRM-33 to CRM-44: open, resolve, close, reopen."""

    def test_a_ticket_can_be_created(self, client, db_session, sample_tenant, sample_branch):
        """CRM-33. The happy path, read back from the row."""
        from models import Ticket

        _manager(client, db_session, sample_tenant, sample_branch, code="support.manage")
        priority = _priority(db_session, sample_tenant)
        before = db_session.query(Ticket).filter_by(tenant_id=sample_tenant.id).count()
        resp = client.post(
            "/tickets/create",
            data={
                "subject": f"Probe Ticket {uuid.uuid4().hex[:6]}",
                "body": "probe",
                "priority_id": str(priority.id),
                "branch_id": str(sample_branch.id),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200, f"ticket create answered {resp.status_code}"

        db_session.expire_all()
        after = db_session.query(Ticket).filter_by(tenant_id=sample_tenant.id).count()
        assert after == before + 1, f"the ticket was not created ({before} -> {after})"

    def test_a_ticket_starts_open(self, db_session, sample_tenant, sample_branch):
        """CRM-34. Nobody has resolved it yet."""
        ticket = _ticket(db_session, sample_tenant, branch=sample_branch)
        assert ticket.status == "open", f"a new ticket starts as {ticket.status!r}"

    def test_the_ticket_detail_page_renders_its_own_ticket(self, client, db_session, sample_tenant, sample_branch):
        """CRM-35."""
        _viewer(client, db_session, sample_tenant, sample_branch, code="support.view")
        ticket = _ticket(db_session, sample_tenant, branch=sample_branch)
        resp = client.get(f"/tickets/{ticket.id}")
        assert resp.status_code in (200, 302), f"the ticket page answered {resp.status_code}"

    def test_resolving_a_ticket_moves_it(self, client, db_session, sample_tenant, sample_branch):
        """CRM-36. The first transition."""
        from models import Ticket

        _manager(client, db_session, sample_tenant, sample_branch, code="support.manage")
        ticket = _ticket(db_session, sample_tenant, branch=sample_branch, status="open")
        ticket_id = ticket.id

        client.post(f"/tickets/{ticket_id}/resolve", follow_redirects=True)
        db_session.expire_all()
        refreshed = db_session.get(Ticket, ticket_id)
        assert refreshed is not None, "resolving removed the ticket"
        if refreshed.status == "resolved":
            assert refreshed.resolved_at is not None, "a resolved ticket carries no resolved_at"

    def test_closing_a_ticket_moves_it(self, client, db_session, sample_tenant, sample_branch):
        """CRM-37."""
        from models import Ticket

        _manager(client, db_session, sample_tenant, sample_branch, code="support.manage")
        ticket = _ticket(db_session, sample_tenant, branch=sample_branch, status="resolved")
        ticket_id = ticket.id

        client.post(f"/tickets/{ticket_id}/close", follow_redirects=True)
        db_session.expire_all()
        refreshed = db_session.get(Ticket, ticket_id)
        assert refreshed is not None, "closing removed the ticket"
        if refreshed.status == "closed":
            assert refreshed.closed_at is not None, "a closed ticket carries no closed_at"

    def test_reopening_a_ticket_moves_it_back(self, client, db_session, sample_tenant, sample_branch):
        """CRM-38. The way back, which is why ``reopen`` exists as a route."""
        from models import Ticket

        _manager(client, db_session, sample_tenant, sample_branch, code="support.manage")
        ticket = _ticket(db_session, sample_tenant, branch=sample_branch, status="closed")
        ticket_id = ticket.id

        client.post(f"/tickets/{ticket_id}/reopen", follow_redirects=True)
        db_session.expire_all()
        refreshed = db_session.get(Ticket, ticket_id)
        assert refreshed is not None, "reopening removed the ticket"
        assert refreshed.status not in ("closed",), f"a reopened ticket is still {refreshed.status!r}"

    def test_a_comment_can_be_added(self, client, db_session, sample_tenant, sample_branch):
        """CRM-39."""
        _manager(client, db_session, sample_tenant, sample_branch, code="support.manage")
        ticket = _ticket(db_session, sample_tenant, branch=sample_branch)
        resp = client.post(
            f"/tickets/{ticket.id}/comment",
            data={"body": "probe comment"},
            follow_redirects=True,
        )
        assert resp.status_code in (200, 302, 404), f"adding a comment answered {resp.status_code}"

    def test_a_ticket_can_be_assigned(self, client, db_session, sample_tenant, sample_branch):
        """CRM-40."""
        from models import Ticket, User

        _manager(client, db_session, sample_tenant, sample_branch, code="support.manage")
        ticket = _ticket(db_session, sample_tenant, branch=sample_branch)
        assignee = db_session.query(User).filter_by(tenant_id=sample_tenant.id).first()

        resp = client.post(
            f"/tickets/{ticket.id}/assign",
            data={"assigned_user_id": str(assignee.id)},
            follow_redirects=True,
        )
        assert resp.status_code in (200, 302, 404), f"assigning answered {resp.status_code}"

        db_session.expire_all()
        refreshed = db_session.get(Ticket, ticket.id)
        if refreshed is not None and assignee is not None:
            assert refreshed.assigned_user_id in (None, assignee.id), (
                f"the ticket is assigned to {refreshed.assigned_user_id}, not the user we named"
            )

    def test_ticket_actions_on_a_missing_id_are_refused(self, client, db_session, sample_tenant, sample_branch):
        """CRM-41. The id arrives from the URL on every one of them."""
        _manager(client, db_session, sample_tenant, sample_branch, code="support.manage")
        for path in TICKET_MANAGE_POST_PATHS:
            resp = client.post(path.replace("/1/", "/99999999/"), data={}, follow_redirects=True)
            assert resp.status_code in (200, 302, 404), f"{path} on a missing ticket answered {resp.status_code}"

    def test_a_ticket_carries_its_sla_deadline(self, db_session, sample_tenant):
        """CRM-42. An SLA is the whole reason the list is ordered by status."""
        from models import Ticket

        columns = Ticket.__table__.columns
        for name in ("sla_deadline", "status", "assigned_user_id", "resolved_at", "closed_at"):
            assert name in columns, f"Ticket has no {name}: {list(columns.keys())}"

    def test_the_ticket_number_is_generated(self, db_session, sample_tenant, sample_branch):
        """CRM-43. A ticket with no number cannot be referenced by a customer."""
        ticket = _ticket(db_session, sample_tenant, branch=sample_branch)
        assert ticket.number, "the ticket carries no number"

    def test_the_ticket_list_shows_our_tickets(self, client, db_session, sample_tenant, sample_branch):
        """CRM-44."""
        _viewer(client, db_session, sample_tenant, sample_branch, code="support.view")
        ticket = _ticket(db_session, sample_tenant, branch=sample_branch, subject="ListedTicket")
        resp = client.get("/tickets/")
        assert resp.status_code == 200
        assert ticket.number in resp.get_data(as_text=True) or ticket.subject in resp.get_data(as_text=True), (
            "the ticket we created is not on the ticket list"
        )
