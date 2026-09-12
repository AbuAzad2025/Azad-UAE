"""Cov5: project_service — flush-failure + detail-query arcs."""

from __future__ import annotations

import pytest


def _patch_tenant(mocker, tenant_id):
    mocker.patch("services.project_service.get_active_tenant_id", return_value=tenant_id)
    mocker.patch("services.project_service.is_global_owner_user", return_value=False)
    mocker.patch("services.project_service.branch_scope_id_for", return_value=None)


def test_create_project_flush_failure(mocker, db_session, sample_user, sample_tenant):
    from extensions import db
    from services.project_service import ProjectService

    _patch_tenant(mocker, sample_tenant.id)
    mocker.patch.object(db.session, "flush", side_effect=RuntimeError("db down"))
    with pytest.raises(RuntimeError, match="db down"):
        ProjectService.create_project({"name": "Boom"}, sample_user)


def test_detail_queries(db_session, sample_user, sample_tenant, mocker):
    from services.project_service import ProjectService

    _patch_tenant(mocker, sample_tenant.id)
    project = ProjectService.create_project({"name": "Detail5"}, sample_user)
    assert len(ProjectService.stages_for_project(project.id)) == 3
    assert ProjectService.tasks_for_project(project.id) == []
    assert ProjectService.members_for_project(project.id) == []
    assert ProjectService.stages_for_project(999999999) == []
    assert ProjectService.active_users_for_tenant(None) == []
    users = ProjectService.active_users_for_tenant(sample_tenant.id)
    assert any(u.id == sample_user.id for u in users)
