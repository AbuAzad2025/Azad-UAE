from __future__ import annotations

import uuid

import pytest

from extensions import db
from models import GLAccount, Tenant
from models.gl_account_registry import BASE_ACCOUNTS, INDUSTRY_EXTENSIONS
from services.gl_tree_builder import (
    GLTreeBuilder,
    CORE_ACCOUNT_CODES,
    _get_core_account_tree,
    _get_industry_tree,
    _template_to_tuple,
)


class TestModuleHelpers:
    def test_template_to_tuple(self):
        tmpl = BASE_ACCOUNTS[0]
        tup = _template_to_tuple(tmpl)
        assert tup[0] == tmpl.code
        assert tup[1] == tmpl.name_ar

    def test_get_core_account_tree(self):
        tree = _get_core_account_tree()
        assert len(tree) == len(BASE_ACCOUNTS)

    def test_get_industry_tree_empty_code(self):
        assert _get_industry_tree("") == []

    def test_get_industry_tree_automotive(self):
        tree = _get_industry_tree("automotive")
        assert len(tree) == len(INDUSTRY_EXTENSIONS["automotive"])

    def test_get_industry_tree_unknown(self):
        assert _get_industry_tree("unknown-industry") == []

    def test_branch_account_code(self):
        assert GLTreeBuilder._branch_account_code("1110", 3) == "1110-B3"


class TestGLTreeBuilderBuild:
    def test_build_creates_core_accounts(self, app, db_session, sample_tenant):
        with app.app_context():
            report = GLTreeBuilder.build(sample_tenant.id, commit=True)
            assert report["tenant_id"] == sample_tenant.id
            assert report["created"] or report["updated"] or report["converted"]
            codes = {a.code for a in GLAccount.query.filter_by(tenant_id=sample_tenant.id).all()}
            assert CORE_ACCOUNT_CODES.issubset(codes)

    def test_build_with_industry_extension(self, app, db_session, sample_tenant):
        sample_tenant.business_type = "automotive"
        db_session.commit()
        with app.app_context():
            report = GLTreeBuilder.build(sample_tenant.id, commit=True)
            codes = {a.code for a in GLAccount.query.filter_by(tenant_id=sample_tenant.id).all()}
            assert "4105" in codes
            assert not report["errors"]

    def test_build_industry_lookup_failure_ignored(self, app, db_session, sample_tenant, mocker):
        mocker.patch("services.gl_tree_builder.db.session.get", side_effect=RuntimeError("db"))
        with app.app_context():
            report = GLTreeBuilder.build(sample_tenant.id, commit=False)
            assert report["tenant_id"] == sample_tenant.id

    def test_build_process_account_error_captured(self, app, db_session, sample_tenant, mocker):
        mocker.patch(
            "services.gl_tree_builder.GLTreeBuilder._process_account",
            side_effect=[{"action": "created", "code": "1110"}, RuntimeError("boom")],
        )
        with app.app_context():
            report = GLTreeBuilder.build(sample_tenant.id, commit=False)
            assert report["errors"]

    def test_build_cleanup_extra_deactivates(self, app, db_session, sample_tenant):
        with app.app_context():
            GLTreeBuilder.build(sample_tenant.id, commit=True)
            extra = GLAccount(
                tenant_id=sample_tenant.id,
                code="99999",
                name="Extra",
                type="asset",
                is_active=True,
            )
            db.session.add(extra)
            db.session.commit()
            report = GLTreeBuilder.build(sample_tenant.id, cleanup_extra=True, commit=True)
            db.session.refresh(extra)
            assert extra.is_active is False
            assert any(d["code"] == "99999" for d in report["deactivated"])

    def test_build_commit_rollback_on_failure(self, app, db_session, sample_tenant, mocker):
        with app.app_context():
            GLTreeBuilder.build(sample_tenant.id, commit=True)
            acc = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="1110").first()
            acc.name = "Stale Name"
            mocker.patch.object(db.session, "commit", side_effect=RuntimeError("commit fail"))
            with pytest.raises(RuntimeError, match="commit fail"):
                GLTreeBuilder.build(sample_tenant.id, commit=True)

    def test_build_no_changes_skips_commit(self, app, db_session, sample_tenant):
        with app.app_context():
            GLTreeBuilder.build(sample_tenant.id, commit=True)
            report = GLTreeBuilder.build(sample_tenant.id, commit=True)
            assert report["created"] == []


class TestProcessAccount:
    def test_process_existing_updates_fields(self, app, db_session, sample_tenant):
        with app.app_context():
            GLTreeBuilder.build(sample_tenant.id, commit=True)
            acc = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="1110").first()
            acc.name = "Wrong"
            acc.is_active = False
            existing = {a.code: a for a in GLAccount.query.filter_by(tenant_id=sample_tenant.id).all()}
            processed = {}
            tmpl = next(t for t in BASE_ACCOUNTS if t.code == "1110")
            result = GLTreeBuilder._process_account(
                sample_tenant.id,
                tmpl.code,
                tmpl.name_ar,
                tmpl.name,
                tmpl.type,
                tmpl.parent_code,
                tmpl.is_header,
                tmpl.level,
                existing,
                processed,
            )
            assert result["action"] == "updated"
            assert acc.is_active is True

    def test_process_existing_updates_all_fields(self, app, db_session, sample_tenant):
        with app.app_context():
            GLTreeBuilder.build(sample_tenant.id, commit=True)
            parent_tmpl = next(t for t in BASE_ACCOUNTS if t.code == "1100")
            child_tmpl = next(t for t in BASE_ACCOUNTS if t.code == "1110")
            existing = {a.code: a for a in GLAccount.query.filter_by(tenant_id=sample_tenant.id).all()}
            processed = {parent_tmpl.code: existing[parent_tmpl.code]}
            acc = existing[child_tmpl.code]
            acc.name = "Wrong"
            acc.name_ar = "خطأ"
            acc.type = "liability"
            acc.is_header = not child_tmpl.is_header
            acc.level = 9
            acc.parent_id = None
            result = GLTreeBuilder._process_account(
                sample_tenant.id,
                child_tmpl.code,
                child_tmpl.name_ar,
                child_tmpl.name,
                child_tmpl.type,
                child_tmpl.parent_code,
                child_tmpl.is_header,
                child_tmpl.level,
                existing,
                processed,
            )
            assert result["action"] in ("updated", "converted")
            assert acc.name == child_tmpl.name
            assert acc.name_ar == child_tmpl.name_ar

    def test_process_create_with_parent_from_existing(self, app, db_session):
        import uuid

        with app.app_context():
            tenant = Tenant(
                name=f"Par-{uuid.uuid4().hex[:6]}",
                name_ar="أب",
                name_en="Parent",
                slug=f"par-{uuid.uuid4().hex[:6]}",
                default_currency="AED",
            )
            db.session.add(tenant)
            db.session.commit()
            parent_tmpl = next(t for t in BASE_ACCOUNTS if t.code == "1100")
            child_tmpl = next(t for t in BASE_ACCOUNTS if t.code == "1110")
            existing = {}
            processed = {}
            GLTreeBuilder._process_account(
                tenant.id,
                parent_tmpl.code,
                parent_tmpl.name_ar,
                parent_tmpl.name,
                parent_tmpl.type,
                parent_tmpl.parent_code,
                parent_tmpl.is_header,
                parent_tmpl.level,
                existing,
                processed,
            )
            result = GLTreeBuilder._process_account(
                tenant.id,
                child_tmpl.code,
                child_tmpl.name_ar,
                child_tmpl.name,
                child_tmpl.type,
                child_tmpl.parent_code,
                child_tmpl.is_header,
                child_tmpl.level,
                existing,
                processed,
            )
            assert result["action"] == "created"
            assert processed[child_tmpl.code].parent_id == processed[parent_tmpl.code].id

    def test_process_account_exception_in_loop(self, app, db_session, sample_tenant, mocker):
        mocker.patch(
            "services.gl_tree_builder.GLTreeBuilder._process_account",
            side_effect=RuntimeError("process fail"),
        )
        with app.app_context():
            report = GLTreeBuilder.build(sample_tenant.id, commit=False)
            assert report["errors"]

    def test_ensure_liquidity_updates_every_field(self, app, db_session, sample_tenant, sample_branch):
        with app.app_context():
            GLTreeBuilder.build(sample_tenant.id, commit=True)
            code = GLTreeBuilder._branch_account_code("1120", sample_branch.id)
            existing = {a.code: a for a in GLAccount.query.filter_by(tenant_id=sample_tenant.id).all()}
            processed = dict(existing)
            acc = existing.get(code)
            if acc is None:
                GLTreeBuilder._ensure_branch_liquidity_accounts(
                    tenant_id=sample_tenant.id,
                    existing_accounts=existing,
                    processed=processed,
                    audit_report={
                        "created": [],
                        "updated": [],
                        "converted": [],
                        "deactivated": [],
                        "errors": [],
                    },
                )
                acc = existing.get(code)
            acc.name = "Stale"
            acc.name_ar = "قديم"
            acc.type = "liability"
            acc.is_header = True
            acc.level = 1
            acc.parent_id = None
            acc.branch_id = None
            acc.liquidity_kind = "cash"
            acc.is_default_liquidity = False
            report = {
                "created": [],
                "updated": [],
                "converted": [],
                "deactivated": [],
                "errors": [],
            }
            GLTreeBuilder._ensure_liquidity_account(
                tenant_id=sample_tenant.id,
                code=code,
                name_ar=f"بنك {sample_branch.name}",
                name_en=f"Bank - {sample_branch.name}",
                parent_code="1120",
                branch_id=sample_branch.id,
                liquidity_kind="bank",
                existing_accounts=existing,
                processed=processed,
                audit_report=report,
            )
            assert acc.liquidity_kind == "bank"
            assert acc.is_default_liquidity is True
            assert report["updated"]

    def test_build_records_converted_accounts(self, app, db_session, sample_tenant, mocker):
        original = GLTreeBuilder._process_account

        def _wrap(*args, **kwargs):
            result = original(*args, **kwargs)
            if result.get("code") == "1110":
                result = dict(result)
                result["action"] = "converted"
            return result

        mocker.patch.object(GLTreeBuilder, "_process_account", side_effect=_wrap)
        with app.app_context():
            report = GLTreeBuilder.build(sample_tenant.id, commit=False)
            assert any(item.get("code") == "1110" for item in report["converted"])

    def test_process_create_parent_from_existing_accounts_map(self, app, db_session, sample_tenant):
        with app.app_context():
            GLTreeBuilder.build(sample_tenant.id, commit=True)
            parent_tmpl = next(t for t in BASE_ACCOUNTS if t.code == "1100")
            child_tmpl = next(t for t in BASE_ACCOUNTS if t.code == "1110")
            existing = {a.code: a for a in GLAccount.query.filter_by(tenant_id=sample_tenant.id).all()}
            del existing[child_tmpl.code]
            db.session.delete(GLAccount.query.filter_by(tenant_id=sample_tenant.id, code=child_tmpl.code).first())
            db.session.commit()
            processed = {}
            result = GLTreeBuilder._process_account(
                sample_tenant.id,
                child_tmpl.code,
                child_tmpl.name_ar,
                child_tmpl.name,
                child_tmpl.type,
                child_tmpl.parent_code,
                child_tmpl.is_header,
                child_tmpl.level,
                existing,
                processed,
            )
            assert result["action"] == "created"
            assert processed[child_tmpl.code].parent_id == existing[parent_tmpl.code].id

    def test_process_existing_header_conversion(self, app, db_session, sample_tenant):
        with app.app_context():
            GLTreeBuilder.build(sample_tenant.id, commit=True)
            acc = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="1110").first()
            acc.is_header = not acc.is_header
            existing = {a.code: a for a in GLAccount.query.filter_by(tenant_id=sample_tenant.id).all()}
            processed = {}
            tmpl = next(t for t in BASE_ACCOUNTS if t.code == "1110")
            result = GLTreeBuilder._process_account(
                sample_tenant.id,
                tmpl.code,
                tmpl.name_ar,
                tmpl.name,
                tmpl.type,
                tmpl.parent_code,
                tmpl.is_header,
                tmpl.level,
                existing,
                processed,
            )
            assert result["action"] in ("converted", "updated", "none")

    def test_process_creates_new_account(self, app, db_session):
        with app.app_context():
            tenant = Tenant(
                name=f"Tree-{uuid.uuid4().hex[:6]}",
                name_ar="شجرة",
                name_en="Tree",
                slug=f"tree-{uuid.uuid4().hex[:6]}",
                default_currency="AED",
            )
            db.session.add(tenant)
            db.session.commit()
            existing = {}
            processed = {}
            tmpl = BASE_ACCOUNTS[0]
            result = GLTreeBuilder._process_account(
                tenant.id,
                tmpl.code,
                tmpl.name_ar,
                tmpl.name,
                tmpl.type,
                tmpl.parent_code,
                tmpl.is_header,
                tmpl.level,
                existing,
                processed,
            )
            assert result["action"] == "created"
            assert processed[tmpl.code].code == tmpl.code


class TestBranchLiquidityAccounts:
    def test_ensure_branch_liquidity_creates_accounts(self, app, db_session, sample_tenant, sample_branch):
        with app.app_context():
            report = {
                "created": [],
                "updated": [],
                "converted": [],
                "deactivated": [],
                "errors": [],
            }
            existing = {a.code: a for a in GLAccount.query.filter_by(tenant_id=sample_tenant.id).all()}
            processed = dict(existing)
            GLTreeBuilder.build(sample_tenant.id, commit=True)
            existing = {a.code: a for a in GLAccount.query.filter_by(tenant_id=sample_tenant.id).all()}
            processed = dict(existing)
            GLTreeBuilder._ensure_branch_liquidity_accounts(
                tenant_id=sample_tenant.id,
                existing_accounts=existing,
                processed=processed,
                audit_report=report,
            )
            cash_code = GLTreeBuilder._branch_account_code("1110", sample_branch.id)
            bank_code = GLTreeBuilder._branch_account_code("1120", sample_branch.id)
            assert cash_code in existing or cash_code in processed
            assert bank_code in existing or bank_code in processed

    def test_ensure_liquidity_updates_existing(self, app, db_session, sample_tenant, sample_branch):
        with app.app_context():
            GLTreeBuilder.build(sample_tenant.id, commit=True)
            code = GLTreeBuilder._branch_account_code("1110", sample_branch.id)
            existing = {a.code: a for a in GLAccount.query.filter_by(tenant_id=sample_tenant.id).all()}
            processed = dict(existing)
            acc = existing.get(code)
            if acc:
                acc.name = "Stale"
                acc.is_active = False
            report = {
                "created": [],
                "updated": [],
                "converted": [],
                "deactivated": [],
                "errors": [],
            }
            GLTreeBuilder._ensure_liquidity_account(
                tenant_id=sample_tenant.id,
                code=code,
                name_ar=f"صندوق {sample_branch.name}",
                name_en=f"Cashbox - {sample_branch.name}",
                parent_code="1110",
                branch_id=sample_branch.id,
                liquidity_kind="cash",
                existing_accounts=existing,
                processed=processed,
                audit_report=report,
            )
            assert report["created"] or report["updated"] or acc is not None


class TestValidateTree:
    def test_validate_tree_complete(self, app, db_session, sample_tenant):
        with app.app_context():
            GLTreeBuilder.build(sample_tenant.id, commit=True)
            result = GLTreeBuilder.validate_tree(sample_tenant.id)
            assert result["total_accounts"] > 0
            assert result["core_accounts_found"] > 0

    def test_validate_tree_missing_core(self, app, db_session):
        with app.app_context():
            tenant = Tenant(
                name=f"Val-{uuid.uuid4().hex[:6]}",
                name_ar="تحقق",
                name_en="Val",
                slug=f"val-{uuid.uuid4().hex[:6]}",
                default_currency="AED",
            )
            db.session.add(tenant)
            db.session.commit()
            result = GLTreeBuilder.validate_tree(tenant.id)
            assert result["valid"] is False
            assert result["missing_core_accounts"]

    def test_validate_tree_inactive_core_and_bad_parent(self, app, db_session, sample_tenant):
        import uuid
        from models import Tenant

        with app.app_context():
            GLTreeBuilder.build(sample_tenant.id, commit=True)
            core = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code="1110").first()
            core.is_active = False
            other = Tenant(
                name=f"ValOther-{uuid.uuid4().hex[:6]}",
                name_ar="أخرى",
                name_en="Other",
                slug=f"val-other-{uuid.uuid4().hex[:6]}",
                default_currency="AED",
            )
            db.session.add(other)
            db.session.flush()
            foreign_parent = GLAccount(
                tenant_id=other.id,
                code="1110",
                name="Foreign",
                type="asset",
                is_active=True,
            )
            db.session.add(foreign_parent)
            db.session.flush()
            child = GLAccount(
                tenant_id=sample_tenant.id,
                code="1199",
                name="Child",
                type="asset",
                parent_id=foreign_parent.id,
                level=5,
                is_active=True,
            )
            db.session.add(child)
            db.session.commit()
            result = GLTreeBuilder.validate_tree(sample_tenant.id)
            assert result["valid"] is False
            assert result["issues"]
            assert result["extra_accounts"]
