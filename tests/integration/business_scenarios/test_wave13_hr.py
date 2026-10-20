"""Wave 13 - people: attendance, leave, departments, contracts and overtime.

The HR blueprint is the only surface in the system that is about a *person*
rather than about money, and that changes what a scenario has to assert. A
ledger scenario asserts that a number moved to the right account. An HR
scenario asserts that a person cannot be affected by someone else's request:
one employee's clock-in must never show up in another employee's attendance
report, one tenant's leave request must not be approvable by another tenant's
manager, and a branch-scoped reader must not see the attendance of a branch
they are not attached to.

The permissions are unusual in a way worth pinning rather than working around.
Ten of the routes want ``hr.view`` or ``hr.manage`` - dot-named, like every
other permission in the system - but the two leave-ledger routes want
``hr:leave_manage``, colon-named, the way the budget permissions are named.
A role granted ``hr.manage`` therefore cannot open the leave ledger, and
HR-05 says so explicitly instead of leaving it as a surprise.

The leave balance ledger is the one place where arithmetic can quietly go
wrong, because ``accrue_leave`` adds to ``taken_days`` and the remaining days
are a derived column: the entitlement comes from the leave type, the carried
days come from the previous year, and the remainder is the difference. HR-30
to HR-33 pin that arithmetic, including the cap on what may be carried over.

Every scenario here is either about a permission boundary or about a state
transition that must not be repeatable, because those are the two things a
person-facing system gets wrong in ways that are embarrassing rather than
merely incorrect.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

#: Every route on the blueprint, grouped by the permission that guards it.
HR_VIEW_PATHS = [
    "/hr/attendance",
    "/hr/leaves",
    "/hr/leaves/request",
    "/hr/departments",
]
HR_MANAGE_PATHS = [
    "/hr/overtime",
]
HR_LEAVE_LEDGER_PATHS = [
    "/hr/leave-ledger",
]
HR_VIEW_POST_PATHS = [
    "/hr/attendance/clock-in",
    "/hr/attendance/clock-out",
]
HR_MANAGE_POST_PATHS = [
    "/hr/departments/create",
    "/hr/contracts/create",
    "/hr/overtime/create",
]
HR_LEAVE_LEDGER_POST_PATHS = [
    "/hr/leave-ledger/accrue",
    "/hr/leave-ledger/carry-forward",
]


def _role(db_session, slug):
    from models import Role

    role = db_session.query(Role).filter_by(slug=slug).first()
    if role is None:
        role = Role(name=slug.replace("_", " ").title(), slug=slug, is_active=True)
        db_session.add(role)
        db_session.commit()
    return role


def _user(db_session, tenant, *, slug="hr-user", permissions=(), branch=None, is_owner=False):
    from models import Permission, User

    role = _role(db_session, slug)
    if permissions:
        role.permissions = Permission.query.filter(Permission.code.in_(list(permissions))).all()
        db_session.add(role)
        db_session.commit()
    unique = uuid.uuid4().hex[:8]
    user = User(
        username=f"hr-{slug}-{unique}",
        email=f"hr-{unique}@example.com",
        full_name=f"HR {slug}",
        tenant_id=tenant.id,
        role_id=role.id,
        branch_id=branch.id if branch else None,
        is_owner=is_owner,
        is_active=True,
    )
    user.set_password("Str0ng!Pass99")
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    # /auth/login refuses to switch users while a session is open - it treats
    # the caller as already signed in. A scenario that needs two actors signs
    # the first one out, otherwise the second login is a no-op and the guard
    # under test is never exercised by the actor it was written for.
    client.get("/auth/logout", follow_redirects=True)
    return client.post(
        "/auth/login",
        data={"username": user.username, "password": "Str0ng!Pass99"},
        follow_redirects=True,
    )


def _with(client, db_session, tenant, branch, codes, slug):
    """A signed-in user carrying exactly ``codes``.

    The role slug is namespaced by the permission set, because _role() reuses a
    role by slug and *replaces* its permissions on every call. Two scenarios
    asking for different grants under one shared slug would silently overwrite
    each other, and the second would then fail a guard for a reason that has
    nothing to do with what it was testing.
    """
    slug = slug + "-" + "-".join(c.replace(".", "-").replace(":", "-") for c in codes)
    user = _user(db_session, tenant, slug=slug, permissions=list(codes), branch=branch)
    _login(client, user)
    return user


def _leave_type(db_session, tenant, *, days_per_year=30, max_carry_forward=0, name="Annual"):
    from models import LeaveType

    leave_type = LeaveType(
        tenant_id=tenant.id,
        name=f"{name}-{uuid.uuid4().hex[:4]}",
        days_per_year=days_per_year,
        max_carry_forward=max_carry_forward,
        is_active=True,
    )
    db_session.add(leave_type)
    db_session.commit()
    return leave_type


def _leave_request(db_session, tenant, user, leave_type, *, state="draft", days=1, branch=None):
    from models import LeaveRequest

    date_from = datetime.now(UTC).date()
    leave = LeaveRequest(
        tenant_id=tenant.id,
        branch_id=branch.id if branch else None,
        user_id=user.id,
        leave_type_id=leave_type.id,
        date_from=date_from,
        date_to=date_from + timedelta(days=days - 1),
        duration=Decimal(str(days)),
        state=state,
        is_active=True,
    )
    db_session.add(leave)
    db_session.commit()
    return leave


def _attendance(db_session, tenant, user, *, branch=None, hours=None, check_out=True):
    """An attendance row.

    The check-in is *now*, not "eight hours ago": the service only finds an
    open record whose check-in is today, so a row from yesterday is invisible
    to it - and a scenario that ran at one in the morning would quietly assert
    something different from the same scenario run at ten in the evening.
    """
    from models import Attendance

    now = datetime.now(UTC)
    att = Attendance(
        tenant_id=tenant.id,
        branch_id=branch.id if branch else None,
        user_id=user.id,
        check_in=now,
        check_out=now if check_out else None,
        work_hours=Decimal(str(hours)) if hours is not None else None,
        state="validated" if check_out else "draft",
    )
    db_session.add(att)
    db_session.commit()
    return att


def _overtime(db_session, tenant, user, *, status="pending", hours="2", branch=None):
    from models import OvertimeEntry

    entry = OvertimeEntry(
        tenant_id=tenant.id,
        user_id=user.id,
        branch_id=branch.id if branch else None,
        overtime_date=datetime.now(UTC).date(),
        hours=Decimal(str(hours)),
        rate_multiplier=Decimal("1.50"),
        overtime_type="standard",
        status=status,
    )
    db_session.add(entry)
    db_session.commit()
    return entry


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


class TestHR01ThePermissionBoundary:
    """HR-01 to HR-08: who may reach the people surface, and who may not."""

    def test_anonymous_is_refused_everywhere(self, client):
        """HR-01."""
        for path in HR_VIEW_PATHS + HR_MANAGE_PATHS + HR_LEAVE_LEDGER_PATHS:
            resp = client.get(path)
            assert resp.status_code in (302, 401, 403), f"{path} answered {resp.status_code}"
            assert "/auth/login" in resp.headers.get("Location", ""), (
                f"{path} did not send an anonymous caller to the login"
            )

    def test_the_hr_permissions_are_seeded(self, db_session):
        """HR-02. A permission the code requires but the seed does not create is a 403 for everyone."""
        from models import Permission

        for code in ("hr.view", "hr.manage", "hr:leave_manage"):
            assert db_session.query(Permission).filter_by(code=code).first() is not None, f"{code} is not seeded"

    def test_hr_view_reaches_the_read_surface(self, client, db_session, demo_tenant, demo_branch):
        """HR-03."""
        _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "reader")
        for path in HR_VIEW_PATHS:
            resp = client.get(path)
            assert resp.status_code == 200, f"{path} answered {resp.status_code}"

    def test_hr_view_does_not_reach_the_overtime_surface(self, client, db_session, demo_tenant, demo_branch):
        """HR-04. The overtime list is behind hr.manage, not hr.view."""
        _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "reader")
        resp = client.get("/hr/overtime")
        assert resp.status_code == 403

    def test_the_leave_ledger_wants_a_differently_named_permission(self, client, db_session, demo_tenant, demo_branch):
        """HR-05. hr:leave_manage is not hr.manage.

        The ledger routes are the only ones on the blueprint guarded by a
        colon-named permission. A manager granted hr.manage - which approves
        leave - still cannot open the ledger, and that asymmetry is pinned here
        rather than left to be discovered.
        """
        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr.manage"], "manager")
        assert client.get("/hr/leave-ledger").status_code == 403

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr:leave_manage"], "ledger")
        assert client.get("/hr/leave-ledger").status_code == 200

    def test_hr_view_does_not_reach_the_management_writes(self, client, db_session, demo_tenant, demo_branch):
        """HR-06. Reading attendance is not the authority to approve a leave."""
        _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "reader")
        leave = _leave_request(
            db_session,
            demo_tenant,
            _user(db_session, demo_tenant, slug="hr-subject"),
            _leave_type(db_session, demo_tenant),
        )
        assert client.post(f"/hr/leaves/{leave.id}/approve").status_code == 403
        assert client.post(f"/hr/leaves/{leave.id}/refuse").status_code == 403
        assert client.post("/hr/departments/create", data={"name": "Nope"}).status_code == 403
        assert client.post("/hr/contracts/create", data={}).status_code == 403
        assert client.post("/hr/overtime/create", data={}).status_code == 403

    def test_the_post_routes_are_gated_too(self, client, db_session, demo_tenant, demo_branch):
        """HR-07. A 405 cannot stand in for a guard: these are POSTs with a body."""
        _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "reader")
        for path in HR_VIEW_POST_PATHS:
            resp = client.post(path, data={})
            assert resp.status_code in (302, 400, 403, 404, 500), f"{path} answered {resp.status_code}"
        # The write verbs are refused for a reader, whatever the body says.
        assert client.post("/hr/attendance/clock-in", data={}).status_code in (302, 403)
        assert client.post("/hr/leave-ledger/accrue", data={}).status_code == 403
        assert client.post("/hr/leave-ledger/carry-forward", data={}).status_code == 403

    def test_view_reports_does_not_grant_the_people_surface(self, client, db_session, demo_tenant, demo_branch):
        """HR-08. A reporting role is not an HR role."""
        _with(client, db_session, demo_tenant, demo_branch, ["view_reports"], "reporter")
        assert client.get("/hr/attendance").status_code == 403
        assert client.get("/hr/leaves").status_code == 403


class TestHR12Attendance:
    """HR-09 to HR-15: the clock-in and clock-out lifecycle."""

    def test_a_clock_in_opens_an_attendance_record(self, client, db_session, demo_tenant, demo_branch):
        """HR-09."""
        user = _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "clocker")
        resp = client.post("/hr/attendance/clock-in", data={"branch_id": str(demo_branch.id)})
        assert resp.status_code in (200, 302)

        from models import Attendance

        att = (
            db_session.query(Attendance)
            .filter_by(user_id=user.id, tenant_id=demo_tenant.id)
            .order_by(Attendance.id.desc())
            .first()
        )
        assert att is not None, "the clock-in left no attendance row"
        assert att.check_out is None
        assert att.state == "draft"

    def test_a_second_clock_in_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """HR-10. Two open records for one person would double the hours."""
        user = _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "clocker")
        _attendance(db_session, demo_tenant, user, branch=demo_branch, check_out=False)
        resp = client.post("/hr/attendance/clock-in", data={"branch_id": str(demo_branch.id)})
        assert resp.status_code in (200, 302)

        from models import Attendance

        open_rows = (
            db_session.query(Attendance)
            .filter_by(user_id=user.id, tenant_id=demo_tenant.id)
            .filter(Attendance.check_out.is_(None))
            .all()
        )
        assert len(open_rows) == 1, f"the second clock-in opened another record: {len(open_rows)}"

    def test_a_clock_out_without_a_clock_in_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """HR-11. There is no hours to report when nothing was opened."""
        _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "clocker")
        resp = client.post("/hr/attendance/clock-out", data={})
        assert resp.status_code in (200, 302)

        from models import Attendance

        rows = db_session.query(Attendance).filter_by(tenant_id=demo_tenant.id).all()
        assert all(row.check_out is not None for row in rows), "a clock-out invented an attendance record"

    def test_a_clock_out_closes_the_open_record_with_its_hours(self, client, db_session, demo_tenant, demo_branch):
        """HR-12."""

        from models import Attendance

        user = _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "clocker")
        att = _attendance(db_session, demo_tenant, user, branch=demo_branch, check_out=False)
        resp = client.post("/hr/attendance/clock-out", data={})
        assert resp.status_code in (200, 302)

        db_session.expire_all()
        closed = db_session.query(Attendance).get(att.id)
        assert closed.check_out is not None, "the clock-out did not close the record"
        assert closed.work_hours is not None and Decimal(str(closed.work_hours)) >= 0

    def test_a_clock_in_for_another_branch_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """HR-13. A branch-scoped employee cannot log attendance into someone else's branch."""
        from models import Branch

        other_branch = Branch(
            tenant_id=demo_tenant.id,
            name=f"Branch {uuid.uuid4().hex[:4]}",
            code=f"BR{uuid.uuid4().hex[:6].upper()}",
            is_active=True,
        )
        db_session.add(other_branch)
        db_session.commit()

        user = _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "clocker")
        resp = client.post("/hr/attendance/clock-in", data={"branch_id": str(other_branch.id)})
        assert resp.status_code in (200, 302)

        from models import Attendance

        rows = db_session.query(Attendance).filter_by(user_id=user.id, tenant_id=demo_tenant.id).all()
        assert not rows, f"a clock-in into another branch was recorded anyway: {rows}"

    def test_the_attendance_report_lists_the_branchs_records(self, client, db_session, demo_tenant, demo_branch):
        """HR-14. The report is the branch's attendance, not the caller's own."""
        user = _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "clocker")
        _attendance(db_session, demo_tenant, user, branch=demo_branch, hours="7.25")
        resp = client.get("/hr/attendance")
        assert resp.status_code == 200
        assert "7.25" in resp.get_data(as_text=True), "the attendance row is not in the report"

    def test_another_tenants_attendance_is_not_in_the_report(self, client, db_session, demo_tenant, demo_branch):
        """HR-15. The report is the tenant's, not everybody's."""
        other_tenant = _other_tenant(db_session)
        foreign = _user(db_session, other_tenant, slug="hr-foreign")
        _attendance(db_session, other_tenant, foreign, hours="9.75")

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "clocker")
        resp = client.get("/hr/attendance")
        assert resp.status_code == 200
        assert "9.75" not in resp.get_data(as_text=True), "another tenant's attendance leaked into the report"

    def test_a_branch_scoped_reader_does_not_see_another_branch(self, client, db_session, demo_tenant, demo_branch):
        """HR-43. The report is scoped to the branch the reader belongs to."""
        from models import Branch

        other_branch = Branch(
            tenant_id=demo_tenant.id,
            name=f"Branch {uuid.uuid4().hex[:4]}",
            code=f"BR{uuid.uuid4().hex[:6].upper()}",
            is_active=True,
        )
        db_session.add(other_branch)
        db_session.commit()

        colleague = _user(db_session, demo_tenant, slug="hr-colleague", branch=other_branch)
        _attendance(db_session, demo_tenant, colleague, branch=other_branch, hours="8.50")

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "clocker")
        resp = client.get("/hr/attendance")
        assert resp.status_code == 200
        assert "8.50" not in resp.get_data(as_text=True), "another branch's attendance leaked into the report"


class TestHR20LeaveRequests:
    """HR-16 to HR-25: requesting, approving and refusing a leave."""

    def test_a_leave_request_is_created_as_a_draft(self, client, db_session, demo_tenant, demo_branch):
        """HR-16."""
        user = _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "requester")
        leave_type = _leave_type(db_session, demo_tenant)
        resp = client.post(
            "/hr/leaves/request",
            data={
                "leave_type_id": str(leave_type.id),
                "date_from": datetime.now(UTC).date().isoformat(),
                "date_to": (datetime.now(UTC).date() + timedelta(days=2)).isoformat(),
                "reason": "Family",
            },
        )
        assert resp.status_code in (200, 302)

        from models import LeaveRequest

        leave = (
            db_session.query(LeaveRequest)
            .filter_by(user_id=user.id, tenant_id=demo_tenant.id)
            .order_by(LeaveRequest.id.desc())
            .first()
        )
        assert leave is not None, "the request left no row"
        assert leave.state == "draft"
        assert Decimal(str(leave.duration)) == Decimal("3"), "the duration does not count the days inclusively"

    def test_a_request_without_a_leave_type_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """HR-17."""
        _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "requester")
        resp = client.post(
            "/hr/leaves/request",
            data={
                "date_from": datetime.now(UTC).date().isoformat(),
                "date_to": datetime.now(UTC).date().isoformat(),
            },
        )
        assert resp.status_code in (200, 302)

        from models import LeaveRequest

        assert db_session.query(LeaveRequest).filter_by(tenant_id=demo_tenant.id).count() == 0

    def test_a_request_that_ends_before_it_starts_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """HR-18."""
        _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "requester")
        leave_type = _leave_type(db_session, demo_tenant)
        start = datetime.now(UTC).date()
        resp = client.post(
            "/hr/leaves/request",
            data={
                "leave_type_id": str(leave_type.id),
                "date_from": start.isoformat(),
                "date_to": (start - timedelta(days=1)).isoformat(),
            },
        )
        assert resp.status_code in (200, 302)

        from models import LeaveRequest

        assert db_session.query(LeaveRequest).filter_by(tenant_id=demo_tenant.id).count() == 0

    def test_a_leave_type_from_another_tenant_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """HR-19. A leave type is tenant data, so it cannot be borrowed."""
        other = _other_tenant(db_session)
        foreign_type = _leave_type(db_session, other, name="Foreign")

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "requester")
        resp = client.post(
            "/hr/leaves/request",
            data={
                "leave_type_id": str(foreign_type.id),
                "date_from": datetime.now(UTC).date().isoformat(),
                "date_to": datetime.now(UTC).date().isoformat(),
            },
        )
        assert resp.status_code in (200, 302)

        from models import LeaveRequest

        assert db_session.query(LeaveRequest).filter_by(tenant_id=demo_tenant.id).count() == 0

    def test_a_manager_approves_a_draft(self, client, db_session, demo_tenant, demo_branch):
        """HR-20."""

        from models import LeaveRequest

        subject = _user(db_session, demo_tenant, slug="hr-subject", branch=demo_branch)
        leave = _leave_request(db_session, demo_tenant, subject, _leave_type(db_session, demo_tenant))

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr.manage"], "manager")
        resp = client.post(f"/hr/leaves/{leave.id}/approve")
        assert resp.status_code in (200, 302)

        db_session.expire_all()
        assert db_session.query(LeaveRequest).get(leave.id).state == "approved"

    def test_approving_twice_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """HR-21. An approved request that could be approved again is a double booking."""

        from models import LeaveRequest

        subject = _user(db_session, demo_tenant, slug="hr-subject", branch=demo_branch)
        leave = _leave_request(db_session, demo_tenant, subject, _leave_type(db_session, demo_tenant), state="approved")

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr.manage"], "manager")
        resp = client.post(f"/hr/leaves/{leave.id}/approve")
        assert resp.status_code in (200, 302)

        db_session.expire_all()
        assert db_session.query(LeaveRequest).get(leave.id).state == "approved", (
            "the second approval moved the request out of the approved state"
        )

    def test_a_refused_request_keeps_its_reason(self, client, db_session, demo_tenant, demo_branch):
        """HR-22. The reason is what the employee is told."""

        from models import LeaveRequest

        subject = _user(db_session, demo_tenant, slug="hr-subject", branch=demo_branch)
        leave = _leave_request(db_session, demo_tenant, subject, _leave_type(db_session, demo_tenant))

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr.manage"], "manager")
        resp = client.post(f"/hr/leaves/{leave.id}/refuse", data={"rejected_reason": "Cover needed"})
        assert resp.status_code in (200, 302)

        db_session.expire_all()
        refused = db_session.query(LeaveRequest).get(leave.id)
        assert refused.state == "refused"
        assert refused.rejected_reason == "Cover needed"

    def test_a_refused_request_cannot_be_refused_again(self, client, db_session, demo_tenant, demo_branch):
        """HR-23."""

        from models import LeaveRequest

        subject = _user(db_session, demo_tenant, slug="hr-subject", branch=demo_branch)
        leave = _leave_request(db_session, demo_tenant, subject, _leave_type(db_session, demo_tenant), state="refused")

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr.manage"], "manager")
        client.post(f"/hr/leaves/{leave.id}/refuse", data={"rejected_reason": "Again"})

        db_session.expire_all()
        still_refused = db_session.query(LeaveRequest).get(leave.id)
        assert still_refused.state == "refused"
        assert still_refused.rejected_reason != "Again", "a second refusal overwrote the original reason"

    def test_another_tenants_leave_cannot_be_approved(self, client, db_session, demo_tenant, demo_branch):
        """HR-24. A leave request is not reachable across the tenant boundary."""

        from models import LeaveRequest

        other = _other_tenant(db_session)
        other_subject = _user(db_session, other, slug="hr-foreign")
        foreign_leave = _leave_request(db_session, other, other_subject, _leave_type(db_session, other))

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr.manage"], "manager")
        resp = client.post(f"/hr/leaves/{foreign_leave.id}/approve")
        assert resp.status_code == 404, f"the cross-tenant approval answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.query(LeaveRequest).get(foreign_leave.id).state == "draft", (
            "another tenant's leave was approved"
        )

    def test_the_leave_list_filters_by_state(self, client, db_session, demo_tenant, demo_branch):
        """HR-25."""
        subject = _user(db_session, demo_tenant, slug="hr-subject", branch=demo_branch)
        leave_type = _leave_type(db_session, demo_tenant)
        _leave_request(db_session, demo_tenant, subject, leave_type, state="draft")
        _leave_request(db_session, demo_tenant, subject, leave_type, state="approved")

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "reader")
        resp = client.get("/hr/leaves?state=approved")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert body.count(subject.full_name) <= 1, "the state filter let a draft through"


class TestHR28DepartmentsAndContracts:
    """HR-26 to HR-30: the two write paths that create people records."""

    def test_a_department_is_created_in_our_tenant(self, client, db_session, demo_tenant, demo_branch):
        """HR-26."""
        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr.manage"], "manager")
        resp = client.post("/hr/departments/create", data={"name": f"Ops {uuid.uuid4().hex[:4]}"})
        assert resp.status_code in (200, 302)

        from models import Department

        dept = db_session.query(Department).filter_by(tenant_id=demo_tenant.id).order_by(Department.id.desc()).first()
        assert dept is not None, "the department was not created"
        assert dept.is_active

    def test_the_department_list_shows_our_own_departments(self, client, db_session, demo_tenant, demo_branch):
        """HR-27."""
        other = _other_tenant(db_session)
        from models import Department

        foreign = Department(tenant_id=other.id, name="Foreign Dept", is_active=True)
        db_session.add(foreign)
        db_session.commit()

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "reader")
        resp = client.get("/hr/departments")
        assert resp.status_code == 200
        assert "Foreign Dept" not in resp.get_data(as_text=True)

    def test_a_contract_is_created_for_an_employee(self, client, db_session, demo_tenant, demo_branch):
        """HR-28."""
        subject = _user(db_session, demo_tenant, slug="hr-subject", branch=demo_branch)
        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr.manage"], "manager")
        resp = client.post(
            "/hr/contracts/create",
            data={
                "user_id": str(subject.id),
                "branch_id": str(demo_branch.id),
                "date_start": datetime.now(UTC).date().isoformat(),
                "wage": "5000",
            },
        )
        assert resp.status_code in (200, 302)

        from models import HRContract

        contract = (
            db_session.query(HRContract)
            .filter_by(tenant_id=demo_tenant.id, user_id=subject.id)
            .order_by(HRContract.id.desc())
            .first()
        )
        assert contract is not None, "the contract was not created"
        assert contract.state == "draft"
        assert Decimal(str(contract.wage)) == Decimal("5000")

    def test_a_contract_for_another_branch_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """HR-29. A branch-scoped manager cannot write a contract into another branch."""
        from models import Branch

        other_branch = Branch(
            tenant_id=demo_tenant.id,
            name=f"Branch {uuid.uuid4().hex[:4]}",
            code=f"BR{uuid.uuid4().hex[:6].upper()}",
            is_active=True,
        )
        db_session.add(other_branch)
        db_session.commit()

        subject = _user(db_session, demo_tenant, slug="hr-subject", branch=demo_branch)
        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr.manage"], "manager")
        resp = client.post(
            "/hr/contracts/create",
            data={
                "user_id": str(subject.id),
                "branch_id": str(other_branch.id),
                "date_start": datetime.now(UTC).date().isoformat(),
                "wage": "5000",
            },
        )
        assert resp.status_code in (200, 302)

        from models import HRContract

        assert db_session.query(HRContract).filter_by(tenant_id=demo_tenant.id, user_id=subject.id).count() == 0, (
            "a contract was written into a branch the manager does not hold"
        )

    def test_a_contract_without_an_employee_is_refused(self, client, db_session, demo_tenant, demo_branch):
        """HR-30. A contract with no person on it is not a contract."""
        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr.manage"], "manager")
        resp = client.post(
            "/hr/contracts/create",
            data={"date_start": datetime.now(UTC).date().isoformat(), "wage": "1000"},
        )
        assert resp.status_code in (200, 302)

        from models import HRContract

        assert db_session.query(HRContract).filter_by(tenant_id=demo_tenant.id).count() == 0


class TestHR32TheLeaveLedger:
    """HR-31 to HR-35: the leave balance arithmetic."""

    def test_the_ledger_needs_its_own_permission(self, client, db_session, demo_tenant, demo_branch):
        """HR-31. A reader may not see the balances of the whole company."""
        _with(client, db_session, demo_tenant, demo_branch, ["hr.view"], "reader")
        resp = client.get("/hr/leave-ledger")
        assert resp.status_code == 403

    def test_a_balance_starts_from_the_leave_type_entitlement(self, client, db_session, demo_tenant, demo_branch):
        """HR-32. The entitlement is the leave type's, not an arbitrary number."""
        subject = _user(db_session, demo_tenant, slug="hr-subject", branch=demo_branch)
        leave_type = _leave_type(db_session, demo_tenant, days_per_year=30)

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr:leave_manage"], "ledger")
        resp = client.post(
            "/hr/leave-ledger/accrue",
            data={
                "user_id": str(subject.id),
                "leave_type_id": str(leave_type.id),
                "days": "0",
                "year": "2026",
            },
        )
        assert resp.status_code in (200, 302)

        from models import LeaveBalance

        balance = (
            db_session.query(LeaveBalance)
            .filter_by(tenant_id=demo_tenant.id, user_id=subject.id, leave_type_id=leave_type.id, year=2026)
            .first()
        )
        assert balance is not None, "no balance was opened for the accrual"
        assert Decimal(str(balance.entitled_days)) == Decimal("30")
        assert Decimal(str(balance.remaining_days)) == Decimal("30")

    def test_accruing_days_takes_them_off_the_remainder(self, client, db_session, demo_tenant, demo_branch):
        """HR-33. The remainder is derived, so it has to follow the accrual."""
        subject = _user(db_session, demo_tenant, slug="hr-subject", branch=demo_branch)
        leave_type = _leave_type(db_session, demo_tenant, days_per_year=30)

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr:leave_manage"], "ledger")
        resp = client.post(
            "/hr/leave-ledger/accrue",
            data={
                "user_id": str(subject.id),
                "leave_type_id": str(leave_type.id),
                "days": "5",
                "year": "2026",
            },
        )
        assert resp.status_code in (200, 302)

        from models import LeaveBalance

        balance = (
            db_session.query(LeaveBalance)
            .filter_by(tenant_id=demo_tenant.id, user_id=subject.id, leave_type_id=leave_type.id, year=2026)
            .first()
        )
        assert balance is not None
        assert Decimal(str(balance.taken_days)) == Decimal("5")
        assert Decimal(str(balance.remaining_days)) == Decimal("25")

    def test_a_carry_forward_is_capped_by_the_leave_type(self, client, db_session, demo_tenant, demo_branch):
        """HR-34. Carrying everything forward is not what the policy says."""
        subject = _user(db_session, demo_tenant, slug="hr-subject", branch=demo_branch)
        leave_type = _leave_type(db_session, demo_tenant, days_per_year=30, max_carry_forward=10)

        from models import LeaveBalance

        db_session.add(
            LeaveBalance(
                tenant_id=demo_tenant.id,
                user_id=subject.id,
                leave_type_id=leave_type.id,
                year=2025,
                entitled_days=Decimal("30"),
                carried_forward=Decimal("0"),
                taken_days=Decimal("0"),
                pending_days=Decimal("0"),
                remaining_days=Decimal("30"),
            )
        )
        db_session.commit()

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr:leave_manage"], "ledger")
        resp = client.post(
            "/hr/leave-ledger/carry-forward",
            data={
                "user_id": str(subject.id),
                "leave_type_id": str(leave_type.id),
                "from_year": "2025",
            },
        )
        assert resp.status_code in (200, 302)

        carried = (
            db_session.query(LeaveBalance)
            .filter_by(tenant_id=demo_tenant.id, user_id=subject.id, leave_type_id=leave_type.id, year=2026)
            .first()
        )
        assert carried is not None, "nothing was carried into 2026"
        assert Decimal(str(carried.carried_forward)) == Decimal("10"), "the carry forward ignored the leave type's cap"

    def test_a_carry_forward_without_a_balance_does_nothing(self, client, db_session, demo_tenant, demo_branch):
        """HR-35. Carrying a year that has no balance is not an error worth a row."""
        subject = _user(db_session, demo_tenant, slug="hr-subject", branch=demo_branch)
        leave_type = _leave_type(db_session, demo_tenant, days_per_year=30, max_carry_forward=10)

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr:leave_manage"], "ledger")
        resp = client.post(
            "/hr/leave-ledger/carry-forward",
            data={
                "user_id": str(subject.id),
                "leave_type_id": str(leave_type.id),
                "from_year": "2024",
            },
        )
        assert resp.status_code in (200, 302)

        from models import LeaveBalance

        assert (
            db_session.query(LeaveBalance).filter_by(tenant_id=demo_tenant.id, user_id=subject.id, year=2025).count()
            == 0
        ), "a carry forward without a source balance invented one"


class TestHR36Overtime:
    """HR-36 to HR-37: the overtime request and its two endings."""

    def test_an_overtime_request_starts_pending(self, client, db_session, demo_tenant, demo_branch):
        """HR-36."""
        subject = _user(db_session, demo_tenant, slug="hr-subject", branch=demo_branch)
        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr.manage"], "manager")
        resp = client.post(
            "/hr/overtime/create",
            data={
                "user_id": str(subject.id),
                "branch_id": str(demo_branch.id),
                "overtime_date": datetime.now(UTC).date().isoformat(),
                "hours": "3",
                "rate_multiplier": "1.5",
            },
        )
        assert resp.status_code in (200, 302)

        from models import OvertimeEntry

        entry = (
            db_session.query(OvertimeEntry)
            .filter_by(tenant_id=demo_tenant.id, user_id=subject.id)
            .order_by(OvertimeEntry.id.desc())
            .first()
        )
        assert entry is not None, "the overtime request was not created"
        assert entry.status == "pending"
        assert Decimal(str(entry.hours)) == Decimal("3")

    def test_a_pending_request_is_approved_once(self, client, db_session, demo_tenant, demo_branch):
        """HR-37. Approving twice would pay the same hours twice."""

        from models import OvertimeEntry

        subject = _user(db_session, demo_tenant, slug="hr-subject", branch=demo_branch)
        entry = _overtime(db_session, demo_tenant, subject, status="pending", branch=demo_branch)

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr.manage"], "manager")
        resp = client.post(f"/hr/overtime/{entry.id}/approve")
        assert resp.status_code in (200, 302)

        db_session.expire_all()
        assert db_session.query(OvertimeEntry).get(entry.id).status == "approved"

        resp = client.post(f"/hr/overtime/{entry.id}/approve")
        assert resp.status_code in (200, 302)
        db_session.expire_all()
        assert db_session.query(OvertimeEntry).get(entry.id).status == ("approved"), (
            "the second approval moved the request out of the approved state"
        )


class TestHR38TheRest:
    """HR-38 to HR-41: rejecting overtime, and the structural invariants."""

    def test_a_rejected_request_keeps_its_reason(self, client, db_session, demo_tenant, demo_branch):
        """HR-38."""

        from models import OvertimeEntry

        subject = _user(db_session, demo_tenant, slug="hr-subject", branch=demo_branch)
        entry = _overtime(db_session, demo_tenant, subject, status="pending", branch=demo_branch)

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr.manage"], "manager")
        resp = client.post(f"/hr/overtime/{entry.id}/reject", data={"reason": "Not budgeted"})
        assert resp.status_code in (200, 302)

        db_session.expire_all()
        rejected = db_session.query(OvertimeEntry).get(entry.id)
        assert rejected.status == "rejected"
        assert rejected.rejected_reason == "Not budgeted"

    def test_another_tenants_overtime_cannot_be_approved(self, client, db_session, demo_tenant, demo_branch):
        """HR-39."""

        from models import OvertimeEntry

        other = _other_tenant(db_session)
        other_subject = _user(db_session, other, slug="hr-foreign")
        foreign_entry = _overtime(db_session, other, other_subject, status="pending")

        _with(client, db_session, demo_tenant, demo_branch, ["hr.view", "hr.manage"], "manager")
        resp = client.post(f"/hr/overtime/{foreign_entry.id}/approve")
        assert resp.status_code == 404, f"the cross-tenant approval answered {resp.status_code}"

        db_session.expire_all()
        assert db_session.query(OvertimeEntry).get(foreign_entry.id).status == "pending", (
            "another tenant's overtime was approved"
        )

    def test_every_people_model_carries_a_tenant_id(self, db_session):
        """HR-40. A people record without a tenant is a record nobody owns."""
        from models import Attendance, Department, HRContract, LeaveBalance, LeaveRequest, OvertimeEntry

        for model in (Attendance, Department, HRContract, LeaveBalance, LeaveRequest, OvertimeEntry):
            column = model.__table__.columns.get("tenant_id")
            assert column is not None, f"{model.__name__} has no tenant_id"
            assert column.nullable is False, f"{model.__name__}.tenant_id is nullable"

    def test_the_money_columns_are_exact_decimals(self, db_session):
        """HR-41. Hours and wages are not floats."""
        from models import Attendance, HRContract, LeaveBalance, OvertimeEntry

        for model, name in (
            (Attendance, "work_hours"),
            (HRContract, "wage"),
            (LeaveBalance, "remaining_days"),
            (OvertimeEntry, "hours"),
        ):
            column = model.__table__.columns.get(name)
            assert column is not None, f"{model.__name__}.{name} does not exist"
            assert "NUMERIC" in str(column.type).upper(), (
                f"{model.__name__}.{name} is {column.type}, not an exact decimal"
            )

    def test_the_scenario_covers_every_hr_route(self, app):
        """HR-42. A scenario that stops covering a route stops being a scenario."""
        known = {
            "/hr/attendance",
            "/hr/attendance/clock-in",
            "/hr/attendance/clock-out",
            "/hr/leaves",
            "/hr/leaves/request",
            "/hr/leaves/<int:leave_id>/approve",
            "/hr/leaves/<int:leave_id>/refuse",
            "/hr/departments",
            "/hr/departments/create",
            "/hr/contracts/create",
            "/hr/leave-ledger",
            "/hr/leave-ledger/accrue",
            "/hr/leave-ledger/carry-forward",
            "/hr/overtime",
            "/hr/overtime/create",
            "/hr/overtime/<int:entry_id>/approve",
            "/hr/overtime/<int:entry_id>/reject",
        }
        live = {rule.rule for rule in app.url_map.iter_rules() if rule.rule.startswith("/hr")}
        assert live == known, f"the HR route inventory moved: {sorted(live ^ known)}"
