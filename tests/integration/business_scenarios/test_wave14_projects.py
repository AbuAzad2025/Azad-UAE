"""Wave 14 - projects, tasks, timesheets and members. Prefix PRJ.

A project is the one surface in the system where time and money meet without
either one being the point. The project itself carries no money; what it
carries is *effort* - planned hours against effective hours, tasks moving
through stages, timesheets accumulating. The rule that has to hold across all
of it is that effort lands on the right project and the right tenant: a timesheet
logged against somebody else's task bills the wrong client, and a task moved
into another project's stage is work that disappears from the gantt.

The project blueprint is therefore mostly about two boundaries. The first is
the permission one - ``project.view`` reads, ``project.manage`` writes - and
the second is the ownership one, pinned here from both sides: another tenant's
project is not readable (PRJ-09), not editable (PRJ-11), and not a place a task
can be moved into (PRJ-16).

The stage rule is the one the service is strictest about. A task carries a
stage, and the stage carries the project it belongs to; moving a task into a
stage of a *different* project is refused rather than silently accepted,
because the gantt is drawn per project and a task in a foreign stage is
invisible in the one chart that matters (PRJ-14, PRJ-16).

The timesheet arithmetic is the third thing worth pinning. Logging hours adds
to the task's effective hours, and the hours have to be positive: a timesheet
of zero hours is a claim that somebody worked and did not (PRJ-18).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

PROJECT_VIEW_PATHS = [
    "/projects/",
    "/projects/1",
]
PROJECT_MANAGE_PATHS = [
    "/projects/create",
    "/projects/1/edit",
]
#: POST-only: asking for them with a GET answers 405 before the guard is even
#: reached, so they are asked for the way they are meant to be called.
PROJECT_MANAGE_POST_PATHS = [
    "/projects/1/tasks",
    "/projects/1/members",
    "/projects/api/move-task",
    "/projects/api/log-timesheet",
]


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="prj-user", permissions=(), branch=None):
    from models import Permission, User

    role = _role(db_session, slug)
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"prj-{slug}-{unique}",
        email=f"prj-{unique}@example.com",
        full_name=f"PRJ {slug}",
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


def _project(db_session, tenant, *, name="Probe Project", branch=None, customer=None):
    """A project with the three stages a created project gets.

    The stages are created here rather than through the service because most of
    these scenarios need a project that already exists, and driving the create
    form for every one of them would be testing the form rather than the rule.
    """
    from models import Project, TaskStage

    project = Project(
        tenant_id=tenant.id,
        branch_id=branch.id if branch else None,
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        customer_id=customer.id if customer else None,
        status="planning",
        is_active=True,
    )
    db_session.add(project)
    db_session.flush()
    for stage_name, sequence, closed, color in (
        ("To Do", 0, False, "#6b7280"),
        ("In Progress", 1, False, "#3b82f6"),
        ("Done", 2, True, "#10b981"),
    ):
        db_session.add(
            TaskStage(
                tenant_id=project.tenant_id,
                project_id=project.id,
                name=stage_name,
                sequence=sequence,
                is_closed=closed,
                color=color,
            )
        )
    db_session.commit()
    return project


def _stages(db_session, project):
    """The three stages a project is created with."""
    from models import TaskStage

    stages = db_session.query(TaskStage).filter_by(project_id=project.id).order_by(TaskStage.sequence).all()
    return stages


def _task(db_session, project, *, name="Probe Task", stage=None, user=None):
    from models import Task

    task = Task(
        tenant_id=project.tenant_id,
        project_id=project.id,
        stage_id=stage.id if stage else None,
        name=f"{name}-{uuid.uuid4().hex[:6]}",
        assigned_user_id=user.id if user else None,
        priority="medium",
        planned_hours=Decimal("8"),
        effective_hours=Decimal("0"),
        is_active=True,
    )
    db_session.add(task)
    db_session.commit()
    return task


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


class TestPRJ01ThePermissionBoundary:
    """PRJ-01 to PRJ-05: who may reach the project surface."""

    def test_anonymous_is_refused_everywhere(self, client):
        """PRJ-01."""
        for path in PROJECT_VIEW_PATHS + PROJECT_MANAGE_PATHS:
            resp = client.get(path)
            assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code}"
            assert "/auth/login" in resp.headers.get("Location", ""), (
                f"{path} did not send an anonymous caller to the login"
            )
        for path in PROJECT_MANAGE_POST_PATHS:
            resp = client.post(path, json={})
            assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code}"

    def test_the_project_permissions_are_seeded(self, db_session):
        """PRJ-02."""
        from models import Permission

        for code in ("project.view", "project.manage"):
            assert db_session.query(Permission).filter_by(code=code).first() is not None, f"{code} is not seeded"

    def test_project_view_reaches_the_read_surface(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-03."""
        _with(client, db_session, demo_tenant, demo_branch, ["project.view"], "reader")
        assert client.get("/projects/").status_code == 200

    def test_project_view_does_not_reach_the_writes(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-04. Reading a project is not the authority to change it."""
        _with(client, db_session, demo_tenant, demo_branch, ["project.view"], "reader")
        project = _project(db_session, demo_tenant, branch=demo_branch)
        assert client.get("/projects/create").status_code == 403
        assert client.get(f"/projects/{project.id}/edit").status_code == 403
        assert client.post(f"/projects/{project.id}/tasks", data={"name": "Nope"}).status_code == 403
        assert client.post(f"/projects/{project.id}/members", data={"user_id": "1"}).status_code == 403
        assert client.post("/projects/api/move-task", json={"task_id": 1, "stage_id": 1}).status_code == 403
        assert client.post("/projects/api/log-timesheet", json={"task_id": 1, "hours": 1}).status_code == 403

    def test_the_scenario_covers_every_project_route(self, app):
        """PRJ-05. A scenario that stops covering a route stops being a scenario."""
        known = {
            "/projects/",
            "/projects/create",
            "/projects/<int:project_id>",
            "/projects/<int:project_id>/edit",
            "/projects/<int:project_id>/tasks",
            "/projects/<int:project_id>/members",
            "/projects/<int:project_id>/gantt",
            "/projects/api/move-task",
            "/projects/api/log-timesheet",
        }
        live = {rule.rule for rule in app.url_map.iter_rules() if rule.rule.startswith("/projects")}
        assert live == known, f"the project route inventory moved: {sorted(live ^ known)}"


class TestPRJ12TheProjectItself:
    """PRJ-06 to PRJ-11: creating, reading and editing a project."""

    def test_a_project_is_created_with_its_default_stages(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-06. A project with no stages is a board nobody can move a card on."""
        _with(client, db_session, demo_tenant, demo_branch, ["project.view", "project.manage"], "manager")
        resp = client.post(
            "/projects/create",
            data={"name": f"Build {uuid.uuid4().hex[:4]}", "status": "planning"},
        )
        assert resp.status_code in (200, 302)

        from models import Project

        project = db_session.query(Project).filter_by(tenant_id=demo_tenant.id).order_by(Project.id.desc()).first()
        assert project is not None, "the project was not created"
        stages = _stages(db_session, project)
        assert len(stages) == 3, f"a new project has {len(stages)} stages, not 3"
        assert [s.name for s in stages] == ["To Do", "In Progress", "Done"]
        assert stages[-1].is_closed, "the last stage is the closed one"

    def test_a_project_without_a_name_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-07."""
        _with(client, db_session, demo_tenant, demo_branch, ["project.view", "project.manage"], "manager")
        resp = client.post("/projects/create", data={"status": "planning"})
        assert resp.status_code in (200, 302)

        from models import Project

        assert db_session.query(Project).filter_by(tenant_id=demo_tenant.id).count() == 0

    def test_the_list_shows_our_own_projects(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-08."""
        project = _project(db_session, demo_tenant, branch=demo_branch)
        _with(client, db_session, demo_tenant, demo_branch, ["project.view"], "reader")
        resp = client.get("/projects/")
        assert resp.status_code == 200
        assert project.name in resp.get_data(as_text=True)

    def test_another_tenants_project_is_not_readable(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-09."""
        other = _other_tenant(db_session)
        foreign = _project(db_session, other, name="Foreign Project")

        _with(client, db_session, demo_tenant, demo_branch, ["project.view"], "reader")
        resp = client.get(f"/projects/{foreign.id}")
        assert resp.status_code in (302, 404), f"the cross-tenant read answered {resp.status_code}"
        assert foreign.name not in resp.get_data(as_text=True)

    def test_editing_a_project_changes_it(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-10."""
        project = _project(db_session, demo_tenant, branch=demo_branch)
        _with(client, db_session, demo_tenant, demo_branch, ["project.view", "project.manage"], "manager")
        resp = client.post(
            f"/projects/{project.id}/edit",
            data={"name": "Renamed Project", "status": "active"},
        )
        assert resp.status_code in (200, 302)

        db_session.expire_all()
        from models import Project

        edited = db_session.query(Project).get(project.id)
        assert edited.name == "Renamed Project"
        assert edited.status == "active"

    def test_another_tenants_project_cannot_be_edited(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-11."""
        other = _other_tenant(db_session)
        foreign = _project(db_session, other, name="Foreign Project")

        _with(client, db_session, demo_tenant, demo_branch, ["project.view", "project.manage"], "manager")
        resp = client.post(f"/projects/{foreign.id}/edit", data={"name": "Hijacked"})
        assert resp.status_code in (302, 404), f"the cross-tenant edit answered {resp.status_code}"

        db_session.expire_all()
        from models import Project

        assert db_session.query(Project).get(foreign.id).name == foreign.name


class TestPRJ20TasksAndStages:
    """PRJ-12 to PRJ-16: the work items and the board they sit on."""

    def test_a_task_is_created_on_the_project(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-12."""
        project = _project(db_session, demo_tenant, branch=demo_branch)
        stage = _stages(db_session, project)[0]

        _with(client, db_session, demo_tenant, demo_branch, ["project.view", "project.manage"], "manager")
        resp = client.post(
            f"/projects/{project.id}/tasks",
            data={"name": "Draw the wireframe", "stage_id": str(stage.id), "planned_hours": "4"},
        )
        assert resp.status_code in (200, 302)

        from models import Task

        task = db_session.query(Task).filter_by(project_id=project.id).order_by(Task.id.desc()).first()
        assert task is not None, "the task was not created"
        assert task.stage_id == stage.id
        assert Decimal(str(task.planned_hours)) == Decimal("4")

    def test_a_task_without_a_name_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-13."""
        project = _project(db_session, demo_tenant, branch=demo_branch)
        _with(client, db_session, demo_tenant, demo_branch, ["project.view", "project.manage"], "manager")
        resp = client.post(f"/projects/{project.id}/tasks", data={"priority": "low"})
        assert resp.status_code in (200, 302)

        from models import Task

        assert db_session.query(Task).filter_by(project_id=project.id).count() == 0

    def test_a_task_cannot_be_created_in_another_projects_stage(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-14. The stage names the project it belongs to."""
        project = _project(db_session, demo_tenant, branch=demo_branch)
        other_project = _project(db_session, demo_tenant, name="Other Project", branch=demo_branch)
        foreign_stage = _stages(db_session, other_project)[0]

        _with(client, db_session, demo_tenant, demo_branch, ["project.view", "project.manage"], "manager")
        resp = client.post(
            f"/projects/{project.id}/tasks",
            data={"name": "Misfiled", "stage_id": str(foreign_stage.id)},
        )
        assert resp.status_code in (200, 302)

        from models import Task

        assert db_session.query(Task).filter_by(project_id=project.id).count() == 0, (
            "a task was filed under another project's stage"
        )

    def test_a_task_moves_to_another_stage(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-15."""
        project = _project(db_session, demo_tenant, branch=demo_branch)
        stages = _stages(db_session, project)
        task = _task(db_session, project, stage=stages[0])

        _with(client, db_session, demo_tenant, demo_branch, ["project.view", "project.manage"], "manager")
        resp = client.post("/projects/api/move-task", json={"task_id": task.id, "stage_id": stages[1].id})
        assert resp.status_code in (200, 302)

        db_session.expire_all()
        from models import Task

        assert db_session.query(Task).get(task.id).stage_id == stages[1].id

    def test_a_task_cannot_move_to_another_projects_stage(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-16. A task in a foreign stage is invisible on the gantt that matters."""
        project = _project(db_session, demo_tenant, branch=demo_branch)
        other_project = _project(db_session, demo_tenant, name="Other Project", branch=demo_branch)
        stages = _stages(db_session, project)
        task = _task(db_session, project, stage=stages[0])
        foreign_stage = _stages(db_session, other_project)[1]

        _with(client, db_session, demo_tenant, demo_branch, ["project.view", "project.manage"], "manager")
        resp = client.post("/projects/api/move-task", json={"task_id": task.id, "stage_id": foreign_stage.id})
        assert resp.status_code == 400, f"the move into a foreign stage answered {resp.status_code}"

        db_session.expire_all()
        from models import Task

        assert db_session.query(Task).get(task.id).stage_id == stages[0].id, (
            "the task was moved into another project's stage"
        )


class TestPRJ24TimesheetsAndMembers:
    """PRJ-17 to PRJ-21: the hours and the people."""

    def test_logging_a_timesheet_adds_the_hours_to_the_task(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-17."""
        project = _project(db_session, demo_tenant, branch=demo_branch)
        task = _task(db_session, project)

        _with(client, db_session, demo_tenant, demo_branch, ["project.view", "project.manage"], "manager")
        resp = client.post("/projects/api/log-timesheet", json={"task_id": task.id, "hours": 2.5})
        assert resp.status_code in (200, 302)

        db_session.expire_all()
        from models import Task, Timesheet

        assert Decimal(str(db_session.query(Task).get(task.id).effective_hours)) == Decimal("2.5")
        assert db_session.query(Timesheet).filter_by(task_id=task.id).count() == 1

    def test_a_timesheet_of_no_hours_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-18. Somebody who worked and did not is not a timesheet."""
        project = _project(db_session, demo_tenant, branch=demo_branch)
        task = _task(db_session, project)

        _with(client, db_session, demo_tenant, demo_branch, ["project.view", "project.manage"], "manager")
        resp = client.post("/projects/api/log-timesheet", json={"task_id": task.id, "hours": 0})
        assert resp.status_code == 400, f"a timesheet of no hours answered {resp.status_code}"

        db_session.expire_all()
        from models import Task, Timesheet

        assert db_session.query(Timesheet).filter_by(task_id=task.id).count() == 0
        assert Decimal(str(db_session.query(Task).get(task.id).effective_hours)) == Decimal("0")

    def test_a_member_is_added_to_the_project(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-19."""
        project = _project(db_session, demo_tenant, branch=demo_branch)
        colleague = _user(db_session, demo_tenant, slug="prj-colleague", branch=demo_branch)

        _with(client, db_session, demo_tenant, demo_branch, ["project.view", "project.manage"], "manager")
        resp = client.post(f"/projects/{project.id}/members", data={"user_id": str(colleague.id), "role": "member"})
        assert resp.status_code in (200, 302)

        from models import ProjectMember

        member = db_session.query(ProjectMember).filter_by(project_id=project.id, user_id=colleague.id).first()
        assert member is not None, "the member was not added"
        assert member.role == "member"

    def test_adding_the_same_member_twice_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-20."""
        project = _project(db_session, demo_tenant, branch=demo_branch)
        colleague = _user(db_session, demo_tenant, slug="prj-colleague", branch=demo_branch)

        _with(client, db_session, demo_tenant, demo_branch, ["project.view", "project.manage"], "manager")
        client.post(f"/projects/{project.id}/members", data={"user_id": str(colleague.id)})
        resp = client.post(f"/projects/{project.id}/members", data={"user_id": str(colleague.id)})
        assert resp.status_code in (200, 302)

        from models import ProjectMember

        assert db_session.query(ProjectMember).filter_by(project_id=project.id, user_id=colleague.id).count() == 1

    def test_the_gantt_answers_the_projects_stages_and_tasks(self, client, db_session, demo_tenant, demo_branch):
        """PRJ-21."""
        project = _project(db_session, demo_tenant, branch=demo_branch)
        stages = _stages(db_session, project)
        task = _task(db_session, project, stage=stages[0], name="Gantt task")

        _with(client, db_session, demo_tenant, demo_branch, ["project.view"], "reader")
        resp = client.get(f"/projects/{project.id}/gantt")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert [s["id"] for s in data["stages"]] == [s.id for s in stages]
        assert [t["id"] for t in data["tasks"]] == [task.id]
        assert data["tasks"][0]["planned_hours"] == 8.0
