from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from extensions import db
from models import CRMLead, CRMStage, CRMActivity, Customer
from services.crm_lead_service import CRMLeadService
from utils.tenanting import set_active_tenant


@pytest.fixture
def crm_stage(db_session, sample_tenant):
    stage = CRMStage(
        tenant_id=sample_tenant.id,
        name="Qualified",
        name_ar="مؤهل",
        sequence=1,
        is_won=False,
        is_lost=False,
        is_active=True,
    )
    db_session.add(stage)
    db_session.flush()
    return stage


@pytest.fixture
def won_stage(db_session, sample_tenant):
    stage = CRMStage(
        tenant_id=sample_tenant.id,
        name="Won",
        sequence=99,
        is_won=True,
        is_lost=False,
        is_active=True,
    )
    db_session.add(stage)
    db_session.flush()
    return stage


@pytest.fixture
def lost_stage(db_session, sample_tenant):
    stage = CRMStage(
        tenant_id=sample_tenant.id,
        name="Lost",
        sequence=100,
        is_won=False,
        is_lost=True,
        is_active=True,
    )
    db_session.add(stage)
    db_session.flush()
    return stage


@pytest.fixture
def crm_lead(db_session, sample_tenant, sample_branch, crm_stage, sample_user):
    lead = CRMLead(
        tenant_id=sample_tenant.id,
        branch_id=sample_branch.id,
        name="Prospect Co",
        email="lead@test.com",
        phone="0501234567",
        stage_id=crm_stage.id,
        assigned_user_id=sample_user.id,
        expected_revenue=Decimal("5000"),
        status="open",
        is_active=True,
    )
    db_session.add(lead)
    db_session.flush()
    return lead


@pytest.fixture
def other_tenant_stage(db_session):
    import uuid
    from models import Tenant
    slug = f"other-{uuid.uuid4().hex[:6]}"
    tenant = Tenant(
        name="Other Co",
        name_ar="شركة أخرى",
        slug=slug,
        email=f"{slug}@test.com",
        country="AE",
        subscription_plan="basic",
    )
    db_session.add(tenant)
    db_session.flush()
    stage = CRMStage(
        tenant_id=tenant.id,
        name="Foreign",
        sequence=1,
        is_active=True,
    )
    db_session.add(stage)
    db_session.flush()
    return stage


class TestValidateTenant:
    def test_rejects_cross_tenant_lead(self, sample_user, crm_lead):
        crm_lead.tenant_id = 99999
        with pytest.raises(ValueError, match="لا ينتمي"):
            CRMLeadService._validate_tenant(crm_lead, sample_user)


class TestBranchScopeCheck:
    def test_rejects_other_branch(self, sample_user):
        sample_user.branch_id = 1
        with pytest.raises(ValueError, match="فرع آخر"):
            CRMLeadService._branch_scope_check(sample_user, branch_id=99)

    def test_global_user_skips_branch_check(self, sample_user):
        sample_user.is_owner = True
        CRMLeadService._branch_scope_check(sample_user, branch_id=999)


class TestCreateLead:
    def test_create_lead_success(self, app, db_session, sample_user, sample_tenant, sample_branch, crm_stage):
        set_active_tenant(sample_tenant.id, user=sample_user)
        lead = CRMLeadService.create_lead(
            {
                "name": "New Lead",
                "email": "new@test.com",
                "branch_id": sample_branch.id,
                "stage_id": crm_stage.id,
                "expected_revenue": "1200.50",
            },
            sample_user,
        )
        assert lead.id is not None
        assert lead.tenant_id == sample_tenant.id
        assert lead.expected_revenue == Decimal("1200.50")
        assert lead.status == "open"

    def test_create_lead_no_active_tenant(self, sample_user):
        sample_user.tenant_id = None
        sample_user.is_owner = False
        with pytest.raises(ValueError, match="لا توجد شركة نشطة"):
            CRMLeadService.create_lead({"name": "X"}, sample_user)

    def test_create_lead_cross_tenant_stage(self, sample_user, sample_tenant, other_tenant_stage):
        set_active_tenant(sample_tenant.id, user=sample_user)
        with pytest.raises(ValueError, match="المرحلة لا تنتمي"):
            CRMLeadService.create_lead(
                {"name": "Bad", "stage_id": other_tenant_stage.id},
                sample_user,
            )

    def test_create_lead_invalid_stage(self, sample_user, sample_tenant):
        set_active_tenant(sample_tenant.id, user=sample_user)
        with pytest.raises(ValueError, match="المرحلة غير صالحة"):
            CRMLeadService.create_lead({"name": "Bad", "stage_id": 999999}, sample_user)

    def test_create_lead_cross_tenant_branch(self, sample_user, sample_tenant, db_session):
        import uuid
        from models import Tenant, Branch
        from unittest.mock import patch
        other = Tenant(
            name="X",
            name_ar="شركة X",
            slug=f"x-{uuid.uuid4().hex[:6]}",
            email="x@t.com",
            country="AE",
            subscription_plan="basic",
        )
        db_session.add(other)
        db_session.flush()
        foreign_branch = Branch(
            tenant_id=other.id,
            name="Foreign",
            code=f"F-{uuid.uuid4().hex[:4]}",
            is_active=True,
        )
        db_session.add(foreign_branch)
        db_session.flush()
        set_active_tenant(sample_tenant.id, user=sample_user)
        with patch("services.crm_lead_service.is_global_user", return_value=True):
            with pytest.raises(ValueError, match="الفرع لا ينتمي"):
                CRMLeadService.create_lead({"name": "Bad", "branch_id": foreign_branch.id}, sample_user)

    def test_create_lead_wrong_branch_scope(self, sample_user, sample_tenant, sample_branch):
        set_active_tenant(sample_tenant.id, user=sample_user)
        sample_user.branch_id = sample_branch.id
        with pytest.raises(ValueError, match="فرع آخر"):
            CRMLeadService.create_lead({"name": "Scoped", "branch_id": sample_branch.id + 999}, sample_user)


class TestUpdateLead:
    def test_update_lead_fields(self, sample_user, crm_lead):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        updated = CRMLeadService.update_lead(
            crm_lead.id,
            {"name": "Updated", "priority": "high", "expected_revenue": "9000"},
            sample_user,
        )
        assert updated.name == "Updated"
        assert updated.priority == "high"
        assert updated.expected_revenue == Decimal("9000")

    def test_update_lead_won_stage(self, sample_user, crm_lead, won_stage):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        updated = CRMLeadService.update_lead(crm_lead.id, {"stage_id": won_stage.id}, sample_user)
        assert updated.status == "won"
        assert updated.closed_at is not None

    def test_update_lead_lost_stage(self, sample_user, crm_lead, lost_stage):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        updated = CRMLeadService.update_lead(crm_lead.id, {"stage_id": lost_stage.id}, sample_user)
        assert updated.status == "lost"

    def test_update_lead_not_found(self, sample_user):
        with pytest.raises(ValueError, match="غير موجود"):
            CRMLeadService.update_lead(999999, {"name": "X"}, sample_user)

    def test_update_lead_invalid_stage(self, sample_user, crm_lead):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        with pytest.raises(ValueError, match="المرحلة غير صالحة"):
            CRMLeadService.update_lead(crm_lead.id, {"stage_id": 999999}, sample_user)

    def test_update_lead_cross_tenant_stage(self, sample_user, crm_lead, other_tenant_stage):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        with pytest.raises(ValueError, match="المرحلة لا تنتمي"):
            CRMLeadService.update_lead(crm_lead.id, {"stage_id": other_tenant_stage.id}, sample_user)


class TestMoveStage:
    def test_move_stage_to_open(self, sample_user, crm_lead, crm_stage):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        moved = CRMLeadService.move_stage(crm_lead.id, crm_stage.id, sample_user)
        assert moved.stage_id == crm_stage.id
        assert moved.status == "open"

    def test_move_stage_won(self, sample_user, crm_lead, won_stage):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        moved = CRMLeadService.move_stage(crm_lead.id, won_stage.id, sample_user)
        assert moved.status == "won"

    def test_move_stage_invalid(self, sample_user, crm_lead):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        with pytest.raises(ValueError, match="المرحلة غير صالحة"):
            CRMLeadService.move_stage(crm_lead.id, 999999, sample_user)

    def test_move_stage_not_found(self, sample_user):
        with pytest.raises(ValueError, match="غير موجود"):
            CRMLeadService.move_stage(999999, 1, sample_user)


class TestGetLead:
    def test_get_lead_success(self, sample_user, crm_lead):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        lead = CRMLeadService.get_lead(crm_lead.id, sample_user)
        assert lead.id == crm_lead.id

    def test_get_lead_cross_tenant(self, sample_user, crm_lead):
        crm_lead.tenant_id = 88888
        with pytest.raises(ValueError, match="لا ينتمي"):
            CRMLeadService.get_lead(crm_lead.id, sample_user)


class TestSearchLeads:
    def test_search_by_status_and_text(self, sample_user, crm_lead):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        results = CRMLeadService.search_leads(
            {"status": "open", "search": "Prospect", "stage_id": crm_lead.stage_id},
            sample_user,
        )
        assert any(r.id == crm_lead.id for r in results)

    def test_search_branch_scoped(self, sample_user, crm_lead, db_session, sample_tenant, sample_branch, crm_stage):
        import uuid
        from models import Branch
        set_active_tenant(sample_tenant.id, user=sample_user)
        sample_user.branch_id = crm_lead.branch_id
        other_branch = Branch(
            tenant_id=sample_tenant.id,
            name="Second Branch",
            code=f"BR-{uuid.uuid4().hex[:4]}",
            is_active=True,
        )
        db_session.add(other_branch)
        db_session.flush()
        other = CRMLead(
            tenant_id=sample_tenant.id,
            branch_id=other_branch.id,
            name="Other Branch Lead",
            status="open",
            is_active=True,
        )
        db_session.add(other)
        db_session.flush()
        results = CRMLeadService.search_leads({}, sample_user)
        ids = {r.id for r in results}
        assert crm_lead.id in ids
        assert other.id not in ids


class TestPipelineStats:
    def test_pipeline_stats_counts(self, sample_user, crm_lead, crm_stage):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        stats = CRMLeadService.get_pipeline_stats(sample_user)
        assert len(stats) >= 1
        row = next(s for s in stats if s["stage"]["id"] == crm_stage.id)
        assert row["count"] >= 1
        assert row["revenue"] >= 0.0

    def test_pipeline_stats_no_tenant(self, sample_user):
        sample_user.tenant_id = None
        assert CRMLeadService.get_pipeline_stats(sample_user) == []


class TestConvertToCustomer:
    def test_convert_creates_customer(self, sample_user, crm_lead):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        crm_lead.email = f"unique-lead-{crm_lead.id}@test.com"
        crm_lead.phone = f"050{crm_lead.id:07d}"
        customer = CRMLeadService.convert_to_customer(crm_lead.id, sample_user)
        assert customer.id is not None
        assert crm_lead.customer_id == customer.id
        assert crm_lead.status == "won"

    def test_convert_idempotent_existing_customer(self, sample_user, crm_lead, sample_customer):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        crm_lead.customer_id = sample_customer.id
        result = CRMLeadService.convert_to_customer(crm_lead.id, sample_user)
        assert result.id == sample_customer.id

    def test_convert_blocks_duplicate_email(self, sample_user, crm_lead, sample_customer):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        crm_lead.email = sample_customer.email
        crm_lead.customer_id = None
        with pytest.raises(ValueError, match="يوجد عميل مسجل بالفعل"):
            CRMLeadService.convert_to_customer(crm_lead.id, sample_user)

    def test_convert_not_found(self, sample_user):
        with pytest.raises(ValueError, match="غير موجود"):
            CRMLeadService.convert_to_customer(999999, sample_user)


class TestConversionKpi:
    def test_compute_conversion_kpi(self, sample_user, crm_lead, won_stage):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        CRMLeadService.move_stage(crm_lead.id, won_stage.id, sample_user)
        kpi = CRMLeadService.compute_conversion_kpi(sample_user)
        assert kpi["total_leads"] >= 1
        assert kpi["total_converted"] >= 1
        assert kpi["conversion_rate"] > 0

    def test_compute_conversion_kpi_with_period(self, sample_user, crm_lead):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        end = datetime(2030, 1, 1, tzinfo=timezone.utc)
        kpi = CRMLeadService.compute_conversion_kpi(sample_user, period_start=start, period_end=end)
        assert "conversion_rate" in kpi

    def test_goal_achievement_zero_target_no_wins(self, sample_user, sample_tenant):
        set_active_tenant(sample_tenant.id, user=sample_user)
        rating = CRMLeadService.compute_goal_achievement_rating(sample_user, 0)
        assert rating["rating"] == 100.0

    def test_goal_achievement_with_target(self, sample_user, crm_lead, won_stage):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        CRMLeadService.move_stage(crm_lead.id, won_stage.id, sample_user)
        rating = CRMLeadService.compute_goal_achievement_rating(sample_user, 1)
        assert rating["achieved"] >= 1
        assert rating["rating"] >= 100.0


class TestAddActivity:
    def test_add_activity_success(self, sample_user, crm_lead):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        activity = CRMLeadService.add_activity(
            crm_lead.id,
            {"activity_type": "call", "summary": "Follow up", "date_deadline": "2025-06-01T10:00:00+00:00"},
            sample_user,
        )
        assert activity.lead_id == crm_lead.id
        assert activity.summary == "Follow up"

    def test_add_activity_not_found(self, sample_user):
        with pytest.raises(ValueError, match="غير موجود"):
            CRMLeadService.add_activity(999999, {"summary": "x"}, sample_user)

    def test_add_activity_branch_scope_denied(self, sample_user, crm_lead):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        sample_user.branch_id = crm_lead.branch_id
        crm_lead.branch_id = crm_lead.branch_id + 500
        with pytest.raises(ValueError, match="فرع آخر"):
            CRMLeadService.add_activity(crm_lead.id, {"summary": "x"}, sample_user)


class TestCreateLeadMockedRollback:
    def test_create_lead_commit_failure(self, mocker, mock_db):
        mock_user = MagicMock()
        mock_user.is_owner = False
        mocker.patch("services.crm_lead_service.get_active_tenant_id", return_value=1)
        mocker.patch("services.crm_lead_service.is_global_owner_user", return_value=False)
        mocker.patch("services.crm_lead_service.is_global_user", return_value=True)
        mocker.patch("services.crm_lead_service.branch_scope_id_for", return_value=None)
        mock_db.session = MagicMock()
        mock_db.session.commit.side_effect = RuntimeError("db fail")
        mocker.patch("services.crm_lead_service.db", mock_db)
        with pytest.raises(RuntimeError, match="db fail"):
            CRMLeadService.create_lead({"name": "Fail"}, mock_user)
        mock_db.session.rollback.assert_called()


class TestSearchFilters:
    def test_search_by_assigned_user(self, sample_user, crm_lead):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        results = CRMLeadService.search_leads(
            {"assigned_user_id": crm_lead.assigned_user_id},
            sample_user,
        )
        assert any(r.id == crm_lead.id for r in results)


class TestCoverageGaps:
    def test_create_lead_tenant_from_branch_when_tid_none(self, app, db_session, mocker, sample_user, sample_branch):
        db_session.flush()
        sample_user.is_owner = True
        mocker.patch("services.crm_lead_service.get_active_tenant_id", return_value=None)
        mocker.patch("services.crm_lead_service.is_global_owner_user", return_value=True)
        mocker.patch("services.crm_lead_service.is_global_user", return_value=True)
        mocker.patch("services.crm_lead_service.branch_scope_id_for", return_value=None)
        with app.app_context():
            lead = CRMLeadService.create_lead(
                {"name": "From Branch", "branch_id": sample_branch.id},
                sample_user,
            )
        assert lead.tenant_id == sample_branch.tenant_id

    def test_update_lead_customer_and_assignee(self, sample_user, crm_lead, sample_customer):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        updated = CRMLeadService.update_lead(
            crm_lead.id,
            {"customer_id": sample_customer.id, "assigned_user_id": sample_user.id},
            sample_user,
        )
        assert updated.customer_id == sample_customer.id
        assert updated.assigned_user_id == sample_user.id

    def test_update_lead_commit_rollback(self, mocker, sample_user, crm_lead):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        mocker.patch("services.crm_lead_service.db.session.commit", side_effect=RuntimeError("upd"))
        mock_rollback = mocker.patch("services.crm_lead_service.db.session.rollback")
        with pytest.raises(RuntimeError, match="upd"):
            CRMLeadService.update_lead(crm_lead.id, {"name": "X"}, sample_user)
        mock_rollback.assert_called_once()

    def test_move_stage_lost(self, sample_user, crm_lead, lost_stage):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        moved = CRMLeadService.move_stage(crm_lead.id, lost_stage.id, sample_user)
        assert moved.status == "lost"

    def test_move_stage_commit_rollback(self, mocker, sample_user, crm_lead, crm_stage):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        mocker.patch("services.crm_lead_service.db.session.commit", side_effect=RuntimeError("move"))
        mock_rollback = mocker.patch("services.crm_lead_service.db.session.rollback")
        with pytest.raises(RuntimeError, match="move"):
            CRMLeadService.move_stage(crm_lead.id, crm_stage.id, sample_user)
        mock_rollback.assert_called_once()

    def test_get_lead_not_found(self, sample_user):
        with pytest.raises(ValueError, match="غير موجود"):
            CRMLeadService.get_lead(999999, sample_user)

    def test_convert_commit_rollback(self, mocker, sample_user, crm_lead):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        crm_lead.email = f"rb-{crm_lead.id}@test.com"
        crm_lead.phone = f"050{crm_lead.id:07d}"
        mocker.patch("services.crm_lead_service.db.session.commit", side_effect=RuntimeError("conv"))
        mock_rollback = mocker.patch("services.crm_lead_service.db.session.rollback")
        with pytest.raises(RuntimeError, match="conv"):
            CRMLeadService.convert_to_customer(crm_lead.id, sample_user)
        mock_rollback.assert_called_once()

    def test_add_activity_commit_rollback(self, mocker, sample_user, crm_lead):
        set_active_tenant(crm_lead.tenant_id, user=sample_user)
        mocker.patch("services.crm_lead_service.db.session.commit", side_effect=RuntimeError("act"))
        mock_rollback = mocker.patch("services.crm_lead_service.db.session.rollback")
        with pytest.raises(RuntimeError, match="act"):
            CRMLeadService.add_activity(crm_lead.id, {"summary": "call"}, sample_user)
        mock_rollback.assert_called_once()
