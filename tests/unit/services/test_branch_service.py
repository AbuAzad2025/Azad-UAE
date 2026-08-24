"""Tests for services/branch_service.py."""

from __future__ import annotations

import pytest

from services.branch_service import BranchService


class TestBranchServiceCreate:
    def test_create_branch_basic(self, db_session, sample_tenant):
        branch = BranchService.create_branch(
            name="Branch A",
            code="BR-A",
            city="Dubai",
            address="Street 1",
            phone="0500000000",
            tenant_id=sample_tenant.id,
        )
        db_session.flush()
        assert branch.id is not None
        assert branch.name == "Branch A"
        assert branch.tenant_id == sample_tenant.id
        assert branch.code == "BR-A"
        assert branch.city == "Dubai"

    def test_create_branch_without_tenant_id(self, db_session):
        branch = BranchService.create_branch(name="No Tenant", code="NO-T")
        # tenant_id is None — model requires NOT NULL, so flush should raise IntegrityError
        assert branch.name == "No Tenant"
        assert branch.tenant_id is None
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_create_branch_is_main_flag(self, db_session, sample_tenant):
        branch = BranchService.create_branch(name="Main", code="MAIN2", is_main=True, tenant_id=sample_tenant.id)
        db_session.flush()
        assert branch.is_main is True

    def test_create_branch_default_is_main_false(self, db_session, sample_tenant):
        branch = BranchService.create_branch(name="Default", code="DEF", tenant_id=sample_tenant.id)
        db_session.flush()
        assert branch.is_main is False

    def test_create_branch_empty_strings(self, db_session, sample_tenant):
        branch = BranchService.create_branch(
            name="Empty", code="", city="", address="", phone="", tenant_id=sample_tenant.id
        )
        db_session.flush()
        assert branch.name == "Empty"
        assert branch.code == ""

    def test_create_branch_unicode_name(self, db_session, sample_tenant):
        branch = BranchService.create_branch(name="فرع دبي الرئيسي", code="DXB", tenant_id=sample_tenant.id)
        db_session.flush()
        assert branch.name == "فرع دبي الرئيسي"

    def test_create_branch_multiple_branches_same_tenant(self, db_session, sample_tenant):
        b1 = BranchService.create_branch(name="B1", code="B1", tenant_id=sample_tenant.id)
        b2 = BranchService.create_branch(name="B2", code="B2", tenant_id=sample_tenant.id)
        db_session.flush()
        assert b1.id != b2.id
        assert b1.tenant_id == sample_tenant.id
        assert b2.tenant_id == sample_tenant.id

    def test_create_branch_does_not_commit_only_flush(self, db_session, sample_tenant):
        # Service uses flush only; caller manages transaction. Ensure flush assigns id.
        branch = BranchService.create_branch(name="FlushOnly", code="FL", tenant_id=sample_tenant.id)
        # before flush, id may be None; after flush id should be set
        assert branch.id is None or isinstance(branch.id, int)
        db_session.flush()
        assert branch.id is not None
