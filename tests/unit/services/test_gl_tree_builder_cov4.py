"""Coverage-4 for services/gl_tree_builder.py — build/heal/validate arcs.

Targets (production lines):
- _template_to_tuple contra default False (13-23).
- _get_industry_tree: falsy industry (31-32), strip/lower + unknown industry
  empty (33-34).
- build: industry-tree exception fallback (77-84), per-account error capture
  (116-117), cleanup_extra deactivation with liquidity_kind guard (124-128),
  commit True atomic arc (138-141) vs commit False flush arc (142-143),
  accounts exposure (147).
- _process_account update arcs: reactivate inactive (174-176), name/name_ar
  (179-185), type (187-189), header conversion (191-195), level (197-199),
  contra non-bool guard (201-204), parent via processed (211-212) vs via
  existing (213-214) vs None (216-218), converted vs updated vs none
  (220-223); create arc with parent variants (230-256).
- _ensure_liquidity_account update path (325-363) vs create path (365-386).
- _branch_account_code int coercion (268-269).
- validate_tree: missing core (414-416), inactive core (418-420),
  extra accounts (425-433), invalid parent (437-441), level mismatch (444-453).
"""

from __future__ import annotations

from types import SimpleNamespace

from models import GLAccount
from services.gl_tree_builder import (
    CORE_ACCOUNT_CODES,
    GLTreeBuilder,
    _get_core_account_tree,
    _get_industry_tree,
    _template_to_tuple,
)


class TestTemplateHelpers:
    def test_template_contra_default_false(self):
        tmpl = SimpleNamespace(
            code="9990", name_ar="ح", name="X", type="asset",
            parent_code=None, is_header=False, level=1,
        )
        assert _template_to_tuple(tmpl)[-1] is False

    def test_template_contra_true(self):
        tmpl = SimpleNamespace(
            code="9990", name_ar="ح", name="X", type="asset",
            parent_code=None, is_header=False, level=1, is_contra=True,
        )
        assert _template_to_tuple(tmpl)[-1] is True

    def test_industry_falsy(self):
        assert _get_industry_tree(None) == []
        assert _get_industry_tree("") == []

    def test_industry_unknown_and_normalized(self):
        assert _get_industry_tree("  NoSuchIndustry  ") == []
        assert isinstance(_get_core_account_tree(), list)
        assert len(_get_core_account_tree()) > 0

    def test_branch_code_int_coercion(self):
        assert GLTreeBuilder._branch_account_code("1110", "7") == "1110-B7"


class TestBuildArcs:
    def test_build_idempotent_and_exposes_accounts(
        self, db_session, sample_tenant, sample_gl_accounts
    ):
        first = GLTreeBuilder.build(sample_tenant.id, commit=False)
        assert "accounts" in first
        assert first["tenant_id"] == sample_tenant.id
        second = GLTreeBuilder.build(sample_tenant.id, commit=False)
        assert second["errors"] == []

    def test_build_commit_true_atomic(self, db_session, sample_tenant, sample_gl_accounts):
        report = GLTreeBuilder.build(sample_tenant.id, commit=True)
        assert report["tenant_id"] == sample_tenant.id

    def test_build_industry_exception_fallback(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch("services.gl_tree_builder.db.session.get", side_effect=RuntimeError("boom"))
        report = GLTreeBuilder.build(sample_tenant.id, commit=False)
        assert report["tenant_id"] == sample_tenant.id

    def test_build_captures_account_errors(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        mocker.patch.object(
            GLTreeBuilder, "_process_account", side_effect=RuntimeError("bad row")
        )
        report = GLTreeBuilder.build(sample_tenant.id, commit=False)
        assert len(report["errors"]) > 0

    def test_cleanup_extra_deactivates_non_core(
        self, db_session, sample_tenant, sample_gl_accounts
    ):
        extra = GLAccount(
            tenant_id=sample_tenant.id, code="COV4-EXTRA-1", name="Extra",
            type="asset", is_active=True,
        )
        db_session.add(extra)
        db_session.flush()
        report = GLTreeBuilder.build(sample_tenant.id, cleanup_extra=True, commit=False)
        assert any(d["code"] == "COV4-EXTRA-1" for d in report["deactivated"])
        assert extra.is_active is False

    def test_cleanup_extra_skips_core_and_liquidity(
        self, db_session, sample_tenant, sample_gl_accounts
    ):
        core_code = next(iter(CORE_ACCOUNT_CODES))
        report = GLTreeBuilder.build(sample_tenant.id, cleanup_extra=True, commit=False)
        assert all(d["code"] != core_code for d in report["deactivated"])


class TestProcessAccountArcs:
    def _existing(self, db_session, sample_tenant, **kwargs):
        base = {
            "tenant_id": sample_tenant.id, "code": "COV4-P1", "name": "EN",
            "name_ar": "AR", "type": "asset", "is_header": False, "level": 2,
            "is_active": True,
        }
        base.update(kwargs)
        acc = GLAccount(**base)
        db_session.add(acc)
        db_session.flush()
        return acc

    def test_reactivate_and_rename_and_retype(
        self, db_session, sample_tenant, sample_gl_accounts
    ):
        acc = self._existing(
            db_session, sample_tenant, is_active=False, name="OLD", name_ar="قديم",
            type="liability", level=9, is_contra=True,
        )
        existing = {acc.code: acc}
        out = GLTreeBuilder._process_account(
            sample_tenant.id, acc.code, "AR", "EN", "asset", None,
            False, 2, existing, {}, is_contra=False,
        )
        assert out["action"] == "updated"
        assert acc.is_active is True
        assert acc.type == "asset"

    def test_header_conversion_action(self, db_session, sample_tenant, sample_gl_accounts):
        acc = self._existing(db_session, sample_tenant, code="COV4-P2", is_header=False)
        existing = {acc.code: acc}
        out = GLTreeBuilder._process_account(
            sample_tenant.id, acc.code, "AR", "EN", "asset", None,
            True, 2, existing, {}, is_contra=False,
        )
        assert out["action"] == "converted"

    def test_no_change_action_none(self, db_session, sample_tenant, sample_gl_accounts):
        acc = self._existing(db_session, sample_tenant, code="COV4-P3", level=2)
        existing = {acc.code: acc}
        out = GLTreeBuilder._process_account(
            sample_tenant.id, acc.code, "AR", "EN", "asset", None,
            False, 2, existing, {}, is_contra=False,
        )
        assert out["action"] == "none"

    def test_non_bool_contra_guarded(self, db_session, sample_tenant, sample_gl_accounts):
        acc = self._existing(db_session, sample_tenant, code="COV4-P4")
        existing = {acc.code: acc}
        out = GLTreeBuilder._process_account(
            sample_tenant.id, acc.code, "AR", "EN", "asset", None,
            False, 2, existing, {}, is_contra="yes",
        )
        assert out["action"] in ("none", "updated")

    def test_parent_via_processed(self, db_session, sample_tenant, sample_gl_accounts):
        parent = self._existing(db_session, sample_tenant, code="COV4-PAR")
        child = self._existing(db_session, sample_tenant, code="COV4-CH")
        existing = {parent.code: parent, child.code: child}
        processed = {parent.code: parent}
        GLTreeBuilder._process_account(
            sample_tenant.id, child.code, "AR", "EN", "asset", parent.code,
            False, 2, existing, processed, is_contra=False,
        )
        assert child.parent_id == parent.id

    def test_create_with_existing_parent(self, db_session, sample_tenant, sample_gl_accounts):
        parent = self._existing(db_session, sample_tenant, code="COV4-NEWPAR")
        existing = {parent.code: parent}
        out = GLTreeBuilder._process_account(
            sample_tenant.id, "COV4-NEWCH", "AR-new", "EN-new", "asset", parent.code,
            False, 3, existing, {}, is_contra=False,
        )
        assert out["action"] == "created"
        assert existing["COV4-NEWCH"].parent_id == parent.id

    def test_create_without_parent(self, db_session, sample_tenant):
        existing = {}
        out = GLTreeBuilder._process_account(
            sample_tenant.id, "COV4-ROOT", "AR-r", "EN-r", "asset", None,
            True, 1, existing, {}, is_contra=False,
        )
        assert out["action"] == "created"
        db_session.rollback()


class TestLiquidityAndValidate:
    def test_liquidity_update_path(
        self, db_session, sample_tenant, sample_branch, sample_gl_accounts
    ):
        # sample_gl_accounts already ensured the branch liquidity account;
        # stale it, then exercise the update path (lines 325-363).
        GLTreeBuilder.build(sample_tenant.id, commit=False)
        existing, processed, report = {}, {}, {
            "created": [], "updated": [], "converted": [],
            "deactivated": [], "errors": [],
        }
        code = GLTreeBuilder._branch_account_code("1110", sample_branch.id)
        acc = GLAccount.query.filter_by(tenant_id=sample_tenant.id, code=code).first()
        assert acc is not None
        acc.name = "stale"
        acc.name_ar = "قديم"
        acc.type = "liability"
        acc.is_header = True
        acc.level = 9
        acc.is_active = False
        db_session.flush()
        existing[code] = acc
        GLTreeBuilder._ensure_liquidity_account(
            tenant_id=sample_tenant.id, code=code, name_ar="صندوق X",
            name_en="Cashbox - X", parent_code="1110", branch_id=sample_branch.id,
            liquidity_kind="cash", existing_accounts=existing,
            processed=processed, audit_report=report,
        )
        assert report["updated"]
        assert acc.type == "asset"
        assert acc.is_header is False

    def test_validate_tree_branches(self, db_session, sample_tenant, sample_gl_accounts):
        ok = GLTreeBuilder.validate_tree(sample_tenant.id)
        assert ok["total_accounts"] > 0

        missing_code = next(iter(CORE_ACCOUNT_CODES))
        doomed = GLAccount.query.filter_by(
            tenant_id=sample_tenant.id, code=missing_code).first()
        if doomed is not None:
            doomed.is_active = False
            db_session.flush()
            bad = GLTreeBuilder.validate_tree(sample_tenant.id)
            assert bad["valid"] is False
            assert any(missing_code in str(i) for i in bad["issues"])
            db_session.rollback()

        import uuid

        from models import Tenant

        unique = uuid.uuid4().hex[:8]
        other_tenant = Tenant(
            name=f"Foreign {unique}", name_ar=f"أجنبي {unique}",
            slug=f"foreign-{unique}", email=f"foreign-{unique}@test.com",
            country="AE", is_active=True,
        )
        db_session.add(other_tenant)
        db_session.flush()
        orphan_parent = GLAccount(
            tenant_id=other_tenant.id, code="COV4-FOREIGN-PAR", name="Foreign",
            type="asset", is_active=True,
        )
        db_session.add(orphan_parent)
        db_session.flush()
        orphan = GLAccount(
            tenant_id=sample_tenant.id, code="COV4-ORPH", name="Orphan",
            type="asset", parent_id=orphan_parent.id, level=5, is_active=True,
        )
        db_session.add(orphan)
        db_session.flush()
        flagged = GLTreeBuilder.validate_tree(sample_tenant.id)
        assert flagged["valid"] is False
        assert any(a["code"] == "COV4-ORPH" for a in flagged["extra_accounts"])
        assert any(
            "غير صالح" in str(i.get("issue", "")) or "يتطابق" in str(i.get("issue", ""))
            for i in flagged["issues"]
        )
        db_session.rollback()
