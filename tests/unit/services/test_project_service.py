from __future__ import annotations

from datetime import datetime, timezone, date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from extensions import db
from models import Project, Task, TaskStage, ProjectMember, Timesheet
from services.project_service import ProjectService


def _patch_tenant(mocker, tenant_id):
    mocker.patch('services.project_service.get_active_tenant_id', return_value=tenant_id)
    mocker.patch('services.project_service.is_global_owner_user', return_value=False)
    mocker.patch('services.project_service.branch_scope_id_for', return_value=None)


class TestCreateProject:
    def test_create_project_with_stages(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'Alpha Project'}, sample_user)
        assert project.name == 'Alpha Project'
        stages = TaskStage.query.filter_by(project_id=project.id).all()
        assert len(stages) == 3
        assert any(s.name == 'Done' and s.is_closed for s in stages)

    def test_create_project_missing_name(self, sample_user, mocker):
        _patch_tenant(mocker, 1)
        with pytest.raises(ValueError, match='اسم المشروع'):
            ProjectService.create_project({}, sample_user)

    def test_create_project_no_tenant(self, sample_user, mocker):
        mocker.patch('services.project_service.get_active_tenant_id', return_value=None)
        mocker.patch('services.project_service.is_global_owner_user', return_value=False)
        with pytest.raises(ValueError, match='شركة نشطة'):
            ProjectService.create_project({'name': 'X'}, sample_user)

    def test_create_with_dates_and_customer(self, db_session, sample_user, sample_tenant, sample_customer, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({
            'name': 'Dated',
            'customer_id': sample_customer.id,
            'date_start': '2026-01-01T00:00:00',
            'date_end': '2026-12-31T00:00:00',
            'status': 'active',
        }, sample_user)
        assert project.customer_id == sample_customer.id
        assert project.status == 'active'


class TestGetUpdateProject:
    def test_get_project(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'Get Me'}, sample_user)
        found = ProjectService.get_project(project.id, sample_user)
        assert found.id == project.id

    def test_get_missing_raises(self, sample_user, mocker):
        _patch_tenant(mocker, 1)
        with pytest.raises(ValueError, match='غير موجود'):
            ProjectService.get_project(99999, sample_user)

    def test_tenant_mismatch_raises(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'Owned'}, sample_user)
        intruder = MagicMock()
        mocker.patch('services.project_service.get_active_tenant_id', return_value=sample_tenant.id + 1)
        with pytest.raises(ValueError, match='شركتك'):
            ProjectService._validate_tenant(project, intruder)

    def test_update_project(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'Old'}, sample_user)
        updated = ProjectService.update_project(project.id, {
            'name': 'New',
            'description': 'desc',
            'color': '#ff0000',
        }, sample_user)
        assert updated.name == 'New'
        assert updated.color == '#ff0000'


class TestListProjects:
    def test_list_projects_tenant_scoped(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        ProjectService.create_project({'name': 'Listed'}, sample_user)
        projects = ProjectService.list_projects(sample_user)
        assert any(p.name == 'Listed' for p in projects)

    def test_list_projects_branch_scope(self, db_session, sample_user, sample_tenant, sample_branch, mocker):
        mocker.patch('services.project_service.get_active_tenant_id', return_value=sample_tenant.id)
        mocker.patch('services.project_service.is_global_owner_user', return_value=False)
        mocker.patch('services.project_service.branch_scope_id_for', return_value=sample_branch.id)
        proj = Project(
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            name='Branch Proj',
        )
        db_session.add(proj)
        db_session.commit()
        projects = ProjectService.list_projects(sample_user)
        assert any(p.name == 'Branch Proj' for p in projects)


class TestTasks:
    def test_create_task(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'Task Proj'}, sample_user)
        stage = TaskStage.query.filter_by(project_id=project.id).first()
        task = ProjectService.create_task(project.id, {
            'name': 'First Task',
            'stage_id': stage.id,
            'planned_hours': '8',
        }, sample_user)
        assert task.name == 'First Task'
        assert task.planned_hours == Decimal('8')

    def test_create_task_missing_name(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'P'}, sample_user)
        with pytest.raises(ValueError, match='اسم المهمة'):
            ProjectService.create_task(project.id, {}, sample_user)

    def test_create_task_invalid_stage(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'P2'}, sample_user)
        with pytest.raises(ValueError, match='المرحلة'):
            ProjectService.create_task(project.id, {'name': 'T', 'stage_id': 99999}, sample_user)

    def test_move_task(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'Move Proj'}, sample_user)
        stages = TaskStage.query.filter_by(project_id=project.id).order_by(TaskStage.sequence).all()
        task = ProjectService.create_task(project.id, {'name': 'Movable'}, sample_user)
        moved = ProjectService.move_task(task.id, stages[1].id, sample_user)
        assert moved.stage_id == stages[1].id

    def test_move_task_invalid_stage(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'Bad Move'}, sample_user)
        other = ProjectService.create_project({'name': 'Other'}, sample_user)
        other_stage = TaskStage.query.filter_by(project_id=other.id).first()
        task = ProjectService.create_task(project.id, {'name': 'Stuck'}, sample_user)
        with pytest.raises(ValueError, match='المرحلة'):
            ProjectService.move_task(task.id, other_stage.id, sample_user)


class TestTimesheet:
    def test_log_timesheet(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'Time Proj'}, sample_user)
        task = ProjectService.create_task(project.id, {'name': 'Work'}, sample_user)
        ts = ProjectService.log_timesheet(task.id, {'hours': '2.5', 'description': 'dev'}, sample_user)
        assert ts.hours == Decimal('2.5')
        db_session.refresh(task)
        assert task.effective_hours == Decimal('2.5')

    def test_log_timesheet_zero_hours(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'Zero'}, sample_user)
        task = ProjectService.create_task(project.id, {'name': 'Idle'}, sample_user)
        with pytest.raises(ValueError, match='أكبر من صفر'):
            ProjectService.log_timesheet(task.id, {'hours': '0'}, sample_user)


class TestGanttAndMembers:
    def test_get_gantt_data(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'Gantt'}, sample_user)
        ProjectService.create_task(project.id, {'name': 'G Task'}, sample_user)
        data = ProjectService.get_gantt_data(project.id, sample_user)
        assert data['project']['name'] == 'Gantt'
        assert len(data['stages']) == 3
        assert len(data['tasks']) == 1

    def test_add_member(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'Team'}, sample_user)
        member = ProjectService.add_member(project.id, sample_user.id, 'lead', sample_user)
        assert member.role == 'lead'

    def test_add_duplicate_member(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'Dup'}, sample_user)
        ProjectService.add_member(project.id, sample_user.id, 'member', sample_user)
        with pytest.raises(ValueError, match='مضاف بالفعل'):
            ProjectService.add_member(project.id, sample_user.id, 'member', sample_user)


class TestProjectEdgeCases:
    def test_update_project_dates_and_customer(self, db_session, sample_user, sample_tenant, sample_customer, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'Edge'}, sample_user)
        updated = ProjectService.update_project(project.id, {
            'date_start': '2026-03-01T00:00:00',
            'date_end': '',
            'customer_id': sample_customer.id,
        }, sample_user)
        assert updated.customer_id == sample_customer.id
        assert updated.date_end is None

    def test_move_task_not_found(self, sample_user, mocker):
        _patch_tenant(mocker, 1)
        with pytest.raises(ValueError, match='غير موجودة'):
            ProjectService.move_task(99999, 1, sample_user)

    def test_log_timesheet_task_not_found(self, sample_user, mocker):
        _patch_tenant(mocker, 1)
        with pytest.raises(ValueError, match='غير موجودة'):
            ProjectService.log_timesheet(99999, {'hours': '1'}, sample_user)

    def test_create_task_with_parent(self, db_session, sample_user, sample_tenant, mocker):
        _patch_tenant(mocker, sample_tenant.id)
        project = ProjectService.create_project({'name': 'Parent Proj'}, sample_user)
        parent = ProjectService.create_task(project.id, {'name': 'Parent Task'}, sample_user)
        child = ProjectService.create_task(project.id, {
            'name': 'Child Task',
            'parent_id': parent.id,
            'date_deadline': '2026-12-01T00:00:00',
        }, sample_user)
        assert child.parent_id == parent.id
        assert child.date_deadline is not None

    def test_create_contract_branch_denied(self, db_session, sample_user, sample_tenant, sample_branch, mocker):
        mocker.patch('services.hr_service.get_active_tenant_id', return_value=sample_tenant.id)
        mocker.patch('services.hr_service.is_global_owner_user', return_value=False)
        mocker.patch('services.hr_service.branch_scope_id_for', return_value=sample_branch.id + 99)
        from services.hr_service import HRService
        with pytest.raises(ValueError, match='فرع آخر'):
            HRService.create_contract({
                'user_id': sample_user.id,
                'branch_id': sample_branch.id,
                'date_start': '2026-01-01',
            }, sample_user)

