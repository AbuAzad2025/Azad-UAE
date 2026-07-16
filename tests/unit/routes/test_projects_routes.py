from __future__ import annotations

from contextlib import ExitStack, contextmanager
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.routes.conftest import (
    _chain_query,
    app_factory,
    bypass_permission_auth,
    unauthenticated_client,
)


def _mock_project(**kwargs):
    proj = MagicMock()
    proj.id = kwargs.get('id', 1)
    proj.tenant_id = kwargs.get('tenant_id', 1)
    proj.name = kwargs.get('name', 'Demo Project')
    proj.to_dict.return_value = {'id': proj.id, 'name': proj.name, 'status': 'planning'}
    return proj


def _mock_task(**kwargs):
    task = MagicMock()
    task.id = kwargs.get('id', 10)
    task.name = kwargs.get('name', 'Task A')
    return task


@contextmanager
def _projects_patches(**kwargs):
    project = kwargs.get('project', _mock_project())
    customers = kwargs.get('customers', [])
    stages = kwargs.get('stages', [MagicMock(id=1, name='To Do', sequence=0)])
    tasks = kwargs.get('tasks', [])
    members = kwargs.get('members', [])
    users = kwargs.get('users', [])
    gantt = kwargs.get('gantt', {
        'project': project.to_dict(),
        'stages': [{'id': 1, 'name': 'To Do'}],
        'tasks': [],
    })

    with ExitStack() as stack:
        stack.enter_context(patch('routes.projects.render_template', return_value='ok'))
        stack.enter_context(patch('routes.projects.ProjectService.list_projects', return_value=kwargs.get('projects', [project])))
        stack.enter_context(patch('routes.projects.ProjectService.get_project', return_value=project))
        stack.enter_context(patch('routes.projects.ProjectService.create_project', return_value=project))
        stack.enter_context(patch('routes.projects.ProjectService.update_project', return_value=project))
        stack.enter_context(patch('routes.projects.ProjectService.create_task', return_value=_mock_task()))
        stack.enter_context(patch('routes.projects.ProjectService.move_task', return_value=_mock_task()))
        stack.enter_context(patch('routes.projects.ProjectService.log_timesheet', return_value=MagicMock(id=5, hours=Decimal('2'))))
        stack.enter_context(patch('routes.projects.ProjectService.get_gantt_data', return_value=gantt))
        stack.enter_context(patch('routes.projects.ProjectService.add_member', return_value=MagicMock()))
        stack.enter_context(patch('routes.projects.get_active_tenant_id', return_value=kwargs.get('tid', 1)))
        stack.enter_context(patch('routes.projects.Customer.query', _chain_query(all=customers)))
        stack.enter_context(patch('routes.projects.TaskStage.query', _chain_query(all=stages)))
        stack.enter_context(patch('routes.projects.Task.query', _chain_query(all=tasks)))
        stack.enter_context(patch('routes.projects.ProjectMember.query', _chain_query(all=members)))
        stack.enter_context(patch('routes.projects.User.query', _chain_query(all=users)))
        stack.enter_context(patch('extensions.limiter.limit', return_value=lambda f: f))
        yield project


@pytest.fixture
def projects_client(app_factory, bypass_permission_auth):
    from routes.projects import projects_bp
    app = app_factory(projects_bp)
    return app.test_client()


class TestProjectsAuth:
    def test_list_requires_login(self, projects_client):
        with _projects_patches(), unauthenticated_client(projects_client):
            resp = projects_client.get('/projects/')
        assert resp.status_code == 401

    def test_list_forbidden_without_permission(self, projects_client, bypass_permission_auth):
        bypass_permission_auth.has_permission.return_value = False
        bypass_permission_auth.is_super_admin.return_value = False
        with _projects_patches(), patch('utils.decorators.is_global_owner_user', return_value=False):
            resp = projects_client.get('/projects/')
        assert resp.status_code == 403


class TestProjectsList:
    def test_list_renders(self, projects_client):
        with _projects_patches():
            resp = projects_client.get('/projects/')
        assert resp.status_code == 200


class TestProjectCreate:
    def test_create_get_form(self, projects_client):
        with _projects_patches():
            resp = projects_client.get('/projects/create')
        assert resp.status_code == 200

    def test_create_post_success(self, projects_client):
        with _projects_patches():
            resp = projects_client.post('/projects/create', data={'name': 'New Proj'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_create_post_error(self, projects_client):
        with _projects_patches(), patch('routes.projects.ProjectService.create_project', side_effect=ValueError('bad')):
            resp = projects_client.post('/projects/create', data={'name': ''})
        assert resp.status_code == 200


class TestProjectDetail:
    def test_detail_renders(self, projects_client):
        with _projects_patches():
            resp = projects_client.get('/projects/1')
        assert resp.status_code == 200

    def test_detail_not_found_redirects(self, projects_client):
        with _projects_patches(), patch('routes.projects.ProjectService.get_project', side_effect=ValueError('missing')):
            resp = projects_client.get('/projects/99', follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_not_found_redirects(self, projects_client):
        with _projects_patches(), patch('routes.projects.ProjectService.get_project', side_effect=ValueError('gone')):
            resp = projects_client.get('/projects/5/edit', follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_get(self, projects_client):
        with _projects_patches():
            resp = projects_client.get('/projects/1/edit')
        assert resp.status_code == 200

    def test_edit_post_success(self, projects_client):
        with _projects_patches():
            resp = projects_client.post('/projects/1/edit', data={'name': 'Updated'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_edit_post_error(self, projects_client):
        with _projects_patches(), patch('routes.projects.ProjectService.update_project', side_effect=ValueError('fail')):
            resp = projects_client.post('/projects/1/edit', data={'name': 'X'})
        assert resp.status_code == 200


class TestProjectTasks:
    def test_add_task(self, projects_client):
        with _projects_patches():
            resp = projects_client.post('/projects/1/tasks', data={'name': 'Task'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_add_task_error(self, projects_client):
        with _projects_patches(), patch('routes.projects.ProjectService.create_task', side_effect=ValueError('no name')):
            resp = projects_client.post('/projects/1/tasks', data={})
        assert resp.status_code == 302

    def test_api_move_task_success(self, projects_client):
        with _projects_patches():
            resp = projects_client.post('/projects/api/move-task', json={'task_id': 1, 'stage_id': 2})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_api_move_task_error(self, projects_client):
        with _projects_patches(), patch('routes.projects.ProjectService.move_task', side_effect=ValueError('bad stage')):
            resp = projects_client.post('/projects/api/move-task', json={'task_id': 1, 'stage_id': 9})
        assert resp.status_code == 400

    def test_api_move_task_missing_key(self, projects_client):
        with _projects_patches():
            resp = projects_client.post('/projects/api/move-task', json={'task_id': 1})
        assert resp.status_code == 400


class TestTimesheetApi:
    def test_log_timesheet_success(self, projects_client):
        with _projects_patches():
            resp = projects_client.post('/projects/api/log-timesheet', json={'task_id': 1, 'hours': '3'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['hours'] == 2.0

    def test_log_timesheet_error(self, projects_client):
        with _projects_patches(), patch('routes.projects.ProjectService.log_timesheet', side_effect=ValueError('zero')):
            resp = projects_client.post('/projects/api/log-timesheet', json={'task_id': 1, 'hours': '0'})
        assert resp.status_code == 400


class TestGanttAndMembers:
    def test_gantt_json(self, projects_client):
        with _projects_patches():
            resp = projects_client.get('/projects/1/gantt')
        assert resp.status_code == 200
        assert 'project' in resp.get_json()

    def test_gantt_not_found(self, projects_client):
        with _projects_patches(), patch('routes.projects.ProjectService.get_gantt_data', side_effect=ValueError('gone')):
            resp = projects_client.get('/projects/99/gantt')
        assert resp.status_code == 404

    def test_add_member_success(self, projects_client):
        with _projects_patches():
            resp = projects_client.post('/projects/1/members', data={'user_id': '2', 'role': 'lead'}, follow_redirects=False)
        assert resp.status_code == 302

    def test_add_member_error(self, projects_client):
        with _projects_patches(), patch('routes.projects.ProjectService.add_member', side_effect=ValueError('dup')):
            resp = projects_client.post('/projects/1/members', data={'user_id': '2'})
        assert resp.status_code == 302

    def test_add_member_missing_user_id(self, projects_client):
        with _projects_patches(), patch('routes.projects.ProjectService.add_member', side_effect=KeyError('user_id')):
            resp = projects_client.post('/projects/1/members', data={})
        assert resp.status_code == 302
