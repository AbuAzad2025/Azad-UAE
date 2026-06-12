"""Project Service unit tests."""
import pytest
from decimal import Decimal
from datetime import datetime, timezone, date
from services.project_service import ProjectService


class TestProjectService:
    def test_create_project(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            data = {
                'name': 'Test Project',
                'status': 'planning',
                'date_start': str(date.today()),
            }
            project = ProjectService.create_project(data, sample_user)
            assert project.id is not None
            assert project.name == 'Test Project'
            assert project.tenant_id == sample_tenant.id

    def test_create_project_no_name_raises(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            with pytest.raises(ValueError):
                ProjectService.create_project({}, sample_user)

    def test_get_project(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            data = {'name': 'P1', 'status': 'planning'}
            project = ProjectService.create_project(data, sample_user)
            fetched = ProjectService.get_project(project.id, sample_user)
            assert fetched.id == project.id

    def test_get_project_wrong_tenant_raises(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            from models import Project
            other = Project(tenant_id=999999, name='Other', status='planning')
            db_session.add(other)
            db_session.flush()
            with pytest.raises(ValueError):
                ProjectService.get_project(other.id, sample_user)

    def test_update_project(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            project = ProjectService.create_project({'name': 'Old', 'status': 'planning'}, sample_user)
            updated = ProjectService.update_project(project.id, {'name': 'New'}, sample_user)
            assert updated.name == 'New'

    def test_list_projects(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            ProjectService.create_project({'name': 'P1', 'status': 'planning'}, sample_user)
            result = ProjectService.list_projects(sample_user)
            assert len(result) >= 1

    def test_create_task(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            project = ProjectService.create_project({'name': 'P1', 'status': 'planning'}, sample_user)
            task = ProjectService.create_task(project.id, {'name': 'T1', 'priority': 'high'}, sample_user)
            assert task.id is not None
            assert task.name == 'T1'
            assert task.project_id == project.id

    def test_create_task_no_name_raises(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            project = ProjectService.create_project({'name': 'P1', 'status': 'planning'}, sample_user)
            with pytest.raises(ValueError):
                ProjectService.create_task(project.id, {}, sample_user)

    def test_move_task(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            project = ProjectService.create_project({'name': 'P1', 'status': 'planning'}, sample_user)
            task = ProjectService.create_task(project.id, {'name': 'T1'}, sample_user)
            from models import TaskStage
            stage = TaskStage.query.filter_by(project_id=project.id).first()
            moved = ProjectService.move_task(task.id, stage.id, sample_user)
            assert moved.stage_id == stage.id

    def test_log_timesheet(self, app, db_session, sample_tenant, sample_user):
        with app.app_context():
            project = ProjectService.create_project({'name': 'P1', 'status': 'planning'}, sample_user)
            task = ProjectService.create_task(project.id, {'name': 'T1'}, sample_user)
            ts = ProjectService.log_timesheet(task.id, {'hours': '2.5', 'description': 'work'}, sample_user)
            assert ts.id is not None
            assert ts.hours == Decimal('2.5')
