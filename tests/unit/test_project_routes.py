"""Tests for Project Management module"""
import pytest
from models import Project, TaskStage, Task, Timesheet, ProjectMember


class TestProjectModels:
    def test_project_creation(self, app, db_session, sample_tenant):
        p = Project(tenant_id=sample_tenant.id, name='Test Project')
        db_session.add(p)
        db_session.commit()
        assert p.id
        assert p.status == 'planning'

    def test_task_stage_creation(self, app, db_session, sample_tenant):
        p = Project(tenant_id=sample_tenant.id, name='Stage Project')
        db_session.add(p)
        db_session.flush()
        s = TaskStage(tenant_id=sample_tenant.id, project_id=p.id, name='To Do', sequence=0)
        db_session.add(s)
        db_session.commit()
        assert len(p.stages) == 1

    def test_task_creation(self, app, db_session, sample_tenant, sample_user):
        p = Project(tenant_id=sample_tenant.id, name='Task Project')
        db_session.add(p)
        db_session.flush()
        t = Task(
            tenant_id=sample_tenant.id,
            project_id=p.id,
            name='First Task',
            assigned_user_id=sample_user.id,
            planned_hours=8,
        )
        db_session.add(t)
        db_session.commit()
        assert t.id
        assert t.project_id == p.id

    def test_timesheet_logging(self, app, db_session, sample_tenant, sample_user):
        p = Project(tenant_id=sample_tenant.id, name='TS Project')
        db_session.add(p)
        db_session.flush()
        t = Task(tenant_id=sample_tenant.id, project_id=p.id, name='TS Task')
        db_session.add(t)
        db_session.flush()
        from datetime import date
        ts = Timesheet(
            tenant_id=sample_tenant.id,
            task_id=t.id,
            user_id=sample_user.id,
            date=date.today(),
            hours=4.5,
        )
        db_session.add(ts)
        db_session.commit()
        assert len(t.timesheets) == 1
        assert float(ts.hours) == 4.5

    def test_task_subtask(self, app, db_session, sample_tenant):
        p = Project(tenant_id=sample_tenant.id, name='Subtask Proj')
        db_session.add(p)
        db_session.flush()
        parent = Task(tenant_id=sample_tenant.id, project_id=p.id, name='Parent Task')
        db_session.add(parent)
        db_session.flush()
        child = Task(tenant_id=sample_tenant.id, project_id=p.id, name='Child Task', parent_id=parent.id)
        db_session.add(child)
        db_session.commit()
        assert len(parent.subtasks) == 1

    def test_project_member(self, app, db_session, sample_tenant, sample_user):
        p = Project(tenant_id=sample_tenant.id, name='Member Project')
        db_session.add(p)
        db_session.flush()
        m = ProjectMember(tenant_id=sample_tenant.id, project_id=p.id, user_id=sample_user.id, role='manager')
        db_session.add(m)
        db_session.commit()
        assert len(p.members) == 1
