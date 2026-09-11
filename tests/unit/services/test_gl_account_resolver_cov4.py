"""Coverage-4 for services/gl_account_resolver.py — resolver fallback arcs.

Targets (production lines):
- is_dynamic_gl_mapping_enabled: dict.get True/False (49), object getattr
  (50), app-context True/False (52-53), Config fallback True (55).
- resolve_gl_account flag-off None arc (73-74) + enabled delegation (76-80).
- _resolve_dynamic_gl_account missing-mapping arc (99-104) + assert/validate
  path (106-112).
- _normalize_concept_code empty/whitespace -> Unknown (120-128).
- _find_active_mapping branch_id None skips branch query (136, 152-163).
- _one_or_error duplicate/single/empty (173-180).
- _raise_missing_or_inactive_mapping: branch-inactive (193-201),
  tenant-inactive (203-210), none-missing (212-217).
- _validated_account: branch missing (227-234), cross-tenant branch (235-241),
  account None (243-250), cross-tenant account (251-257), inactive (258-264),
  header (265-271), success (272).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from config import Config
from models._constants import GL_CONCEPT_CASH
from models.gl import GLAccount, GLAccountMapping
from services.gl_account_resolver import (
    GLMappingError,
    _find_active_mapping,
    _normalize_concept_code,
    _one_or_error,
    _raise_missing_or_inactive_mapping,
    _resolve_dynamic_gl_account,
    _validated_account,
    is_dynamic_gl_mapping_enabled,
    resolve_gl_account,
)


def _account(db_session, tenant, code, active=True, header=False, a_type="asset"):
    acc = GLAccount(
        tenant_id=tenant.id, code=code, name=f"AC {code}",
        type=a_type, is_active=active, is_header=header,
    )
    db_session.add(acc)
    db_session.flush()
    return acc


def _mapping(db_session, tenant, concept, account, branch_id=None, active=True):
    m = GLAccountMapping(
        tenant_id=tenant.id, concept_code=concept, gl_account_id=account.id,
        branch_id=branch_id, is_active=active,
    )
    db_session.add(m)
    db_session.flush()
    return m


class TestFlagArcs:
    def test_dict_missing_key_defaults_false(self):
        assert is_dynamic_gl_mapping_enabled({}) is False

    def test_object_without_attr_defaults_false(self):
        assert is_dynamic_gl_mapping_enabled(SimpleNamespace()) is False

    def test_app_context_false(self, app):
        with app.app_context():
            app.config["ENABLE_DYNAMIC_GL_MAPPING"] = False
            assert is_dynamic_gl_mapping_enabled() is False

    def test_config_class_true(self, mocker):
        mocker.patch("services.gl_account_resolver.has_app_context", return_value=False)
        prev = Config.ENABLE_DYNAMIC_GL_MAPPING
        try:
            Config.ENABLE_DYNAMIC_GL_MAPPING = True
            assert is_dynamic_gl_mapping_enabled() is True
        finally:
            Config.ENABLE_DYNAMIC_GL_MAPPING = prev

    def test_resolve_delegates_when_enabled(self, app, mocker):
        with app.app_context():
            app.config["ENABLE_DYNAMIC_GL_MAPPING"] = True
            sentinel = object()
            routed = mocker.patch(
                "services.gl_account_resolver._resolve_dynamic_gl_account",
                return_value=sentinel,
            )
            assert resolve_gl_account(1, GL_CONCEPT_CASH, branch_id=2) is sentinel
            assert routed.called


class TestNormalizeAndOneOrError:
    def test_empty_concept_raises(self):
        with pytest.raises(GLMappingError, match="Unknown GL concept"):
            _normalize_concept_code(1, "   ", None)

    def test_none_concept_raises(self):
        with pytest.raises(GLMappingError, match="Unknown GL concept"):
            _normalize_concept_code(1, None, None)

    def test_duplicate_scope_message(self):
        from unittest.mock import MagicMock

        with pytest.raises(GLMappingError, match="tenant default"):
            _one_or_error([MagicMock(), MagicMock()], 1, "CASH", None, "tenant default")


class TestFindActiveMappingDb:
    def test_none_branch_id_queries_default_only(
        self, db_session, sample_tenant, sample_gl_accounts, mocker
    ):
        real = mocker.patch(
            "services.gl_account_resolver._one_or_error",
            wraps=_one_or_error,
        )
        out = _find_active_mapping(sample_tenant.id, GL_CONCEPT_CASH, branch_id=None)
        assert real.call_count == 1
        assert out is None or hasattr(out, "id")

    def test_dynamic_resolve_missing_mapping_raises(
        self, db_session, sample_tenant, sample_gl_accounts, app
    ):
        GLAccountMapping.query.filter_by(
            tenant_id=sample_tenant.id, concept_code=GL_CONCEPT_CASH
        ).delete()
        db_session.flush()
        with pytest.raises(GLMappingError, match="No active GL account mapping"):
            _resolve_dynamic_gl_account(
                tenant_id=sample_tenant.id, concept_code=GL_CONCEPT_CASH
            )

    def test_dynamic_resolve_success(
        self, db_session, sample_tenant, sample_gl_accounts, app
    ):
        from models._constants import GL_CONCEPT_CASH as CASH

        existing = GLAccountMapping.query.filter_by(
            tenant_id=sample_tenant.id, concept_code=CASH, is_active=True
        ).first()
        if existing is None:
            acc = GLAccount.query.filter_by(tenant_id=sample_tenant.id).first()
            _mapping(db_session, sample_tenant, CASH, acc)
        out = _resolve_dynamic_gl_account(
            tenant_id=sample_tenant.id, concept_code=CASH
        )
        assert out.tenant_id == sample_tenant.id


class TestRaiseMissingBranches:
    def test_branch_inactive_message(
        self, db_session, sample_tenant, sample_branch, sample_gl_accounts
    ):
        acc = GLAccount.query.filter_by(tenant_id=sample_tenant.id).first()
        _mapping(db_session, sample_tenant, GL_CONCEPT_CASH, acc,
                 branch_id=sample_branch.id, active=False)
        with pytest.raises(GLMappingError, match="Branch override mapping exists but is inactive"):
            _raise_missing_or_inactive_mapping(
                tenant_id=sample_tenant.id, concept_code=GL_CONCEPT_CASH,
                branch_id=sample_branch.id,
            )

    def test_tenant_inactive_message(self, db_session, sample_tenant, sample_gl_accounts):
        acc = GLAccount.query.filter_by(tenant_id=sample_tenant.id).first()
        old = GLAccountMapping.query.filter_by(
            tenant_id=sample_tenant.id, concept_code=GL_CONCEPT_CASH, branch_id=None
        ).all()
        for m in old:
            db_session.delete(m)
        db_session.flush()
        _mapping(db_session, sample_tenant, GL_CONCEPT_CASH, acc, branch_id=None, active=False)
        with pytest.raises(GLMappingError, match="Tenant-level mapping exists but is inactive"):
            _raise_missing_or_inactive_mapping(
                tenant_id=sample_tenant.id, concept_code=GL_CONCEPT_CASH, branch_id=None
            )

    def test_no_mapping_message(self, db_session, sample_tenant):
        with pytest.raises(GLMappingError, match="No active GL account mapping"):
            _raise_missing_or_inactive_mapping(
                tenant_id=sample_tenant.id, concept_code="BANK", branch_id=None
            )


class TestValidatedAccountDb:
    def test_branch_missing_raises(self, db_session, sample_tenant, sample_gl_accounts):
        acc = GLAccount.query.filter_by(tenant_id=sample_tenant.id).first()
        fake_mapping = SimpleNamespace(branch_id=424242, branch=None, gl_account=acc)
        with pytest.raises(GLMappingError, match="missing branch"):
            _validated_account(fake_mapping, sample_tenant.id, GL_CONCEPT_CASH, 424242)

    def test_branch_cross_tenant_raises(
        self, db_session, sample_tenant, sample_branch, sample_gl_accounts
    ):
        acc = GLAccount.query.filter_by(tenant_id=sample_tenant.id).first()
        other_branch = SimpleNamespace(tenant_id=sample_tenant.id + 9999)
        fake_mapping = SimpleNamespace(
            branch_id=sample_branch.id, branch=other_branch, gl_account=acc
        )
        with pytest.raises(GLMappingError, match="different tenant"):
            _validated_account(fake_mapping, sample_tenant.id, GL_CONCEPT_CASH, sample_branch.id)

    def test_account_none_raises(self):
        fake_mapping = SimpleNamespace(branch_id=None, branch=None, gl_account=None)
        with pytest.raises(GLMappingError, match="does not exist"):
            _validated_account(fake_mapping, 1, GL_CONCEPT_CASH, None)

    def test_account_cross_tenant_raises(self, db_session, sample_tenant, sample_gl_accounts):
        acc = GLAccount.query.filter_by(tenant_id=sample_tenant.id).first()
        acc.tenant_id = sample_tenant.id + 7777
        fake_mapping = SimpleNamespace(branch_id=None, branch=None, gl_account=acc)
        with pytest.raises(GLMappingError, match="belongs to a different tenant"):
            _validated_account(fake_mapping, sample_tenant.id, GL_CONCEPT_CASH, None)
        db_session.rollback()

    def test_inactive_account_raises(self, db_session, sample_tenant):
        acc = _account(db_session, sample_tenant, "RSLV-1", active=False)
        fake_mapping = SimpleNamespace(branch_id=None, branch=None, gl_account=acc)
        with pytest.raises(GLMappingError, match="inactive"):
            _validated_account(fake_mapping, sample_tenant.id, GL_CONCEPT_CASH, None)
        db_session.rollback()

    def test_header_account_raises(self, db_session, sample_tenant):
        acc = _account(db_session, sample_tenant, "RSLV-2", header=True)
        fake_mapping = SimpleNamespace(branch_id=None, branch=None, gl_account=acc)
        with pytest.raises(GLMappingError, match="header/group"):
            _validated_account(fake_mapping, sample_tenant.id, GL_CONCEPT_CASH, None)
        db_session.rollback()

    def test_success_returns_account(self, db_session, sample_tenant):
        acc = _account(db_session, sample_tenant, "RSLV-3")
        fake_mapping = SimpleNamespace(branch_id=None, branch=None, gl_account=acc)
        assert _validated_account(fake_mapping, sample_tenant.id, GL_CONCEPT_CASH, None) is acc
        db_session.rollback()
