from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config import Config
from models._constants import GL_CONCEPT_CASH
from services.gl_account_resolver import (
    GLMappingError,
    is_dynamic_gl_mapping_enabled,
    resolve_gl_account,
    _normalize_concept_code,
    _find_active_mapping,
    _one_or_error,
    _raise_missing_or_inactive_mapping,
    _validated_account,
)


class TestFeatureFlag:
    def test_enabled_from_dict_config(self):
        assert (
            is_dynamic_gl_mapping_enabled({"ENABLE_DYNAMIC_GL_MAPPING": True}) is True
        )
        assert (
            is_dynamic_gl_mapping_enabled({"ENABLE_DYNAMIC_GL_MAPPING": False}) is False
        )

    def test_enabled_from_object_config(self):
        cfg = SimpleNamespace(ENABLE_DYNAMIC_GL_MAPPING=True)
        assert is_dynamic_gl_mapping_enabled(cfg) is True

    def test_enabled_from_app_context(self, app):
        with app.app_context():
            app.config["ENABLE_DYNAMIC_GL_MAPPING"] = True
            assert is_dynamic_gl_mapping_enabled() is True

    def test_enabled_fallback_to_config_class(self, mocker):
        mocker.patch("services.gl_account_resolver.has_app_context", return_value=False)
        prev = Config.ENABLE_DYNAMIC_GL_MAPPING
        try:
            Config.ENABLE_DYNAMIC_GL_MAPPING = False
            assert is_dynamic_gl_mapping_enabled() is False
        finally:
            Config.ENABLE_DYNAMIC_GL_MAPPING = prev

    def test_resolve_returns_none_when_disabled(self, app):
        with app.app_context():
            app.config["ENABLE_DYNAMIC_GL_MAPPING"] = False
            assert resolve_gl_account(1, GL_CONCEPT_CASH) is None


class TestGLMappingError:
    def test_message_and_init(self):
        err = GLMappingError(
            tenant_id=1,
            concept_code="CASH",
            branch_id=2,
            issue="test issue",
        )
        assert "tenant_id=1" in str(err)
        assert err.message.endswith("test issue")


class TestNormalizeConcept:
    def test_unknown_concept_raises(self):
        with pytest.raises(GLMappingError, match="Unknown GL concept"):
            _normalize_concept_code(1, "NOT_VALID", None)

    def test_strips_and_uppercases(self):
        assert _normalize_concept_code(1, " cash ", None) == "CASH"


class TestOneOrError:
    def test_duplicate_mappings_raises(self):
        mappings = [MagicMock(), MagicMock()]
        with pytest.raises(GLMappingError, match="Duplicate"):
            _one_or_error(mappings, 1, "CASH", 2, "branch override")

    def test_empty_returns_none(self):
        assert _one_or_error([], 1, "CASH", None, "tenant default") is None

    def test_single_returns_mapping(self):
        mapping = MagicMock()
        assert _one_or_error([mapping], 1, "CASH", None, "tenant default") is mapping


class TestFindActiveMapping:
    def test_prefers_branch_override(self, mocker):
        branch_mapping = MagicMock()
        one = mocker.patch(
            "services.gl_account_resolver._one_or_error",
            side_effect=[branch_mapping, None],
        )
        result = _find_active_mapping(1, "CASH", branch_id=5)
        assert result is branch_mapping
        assert one.call_count == 1

    def test_falls_back_to_tenant_default(self, mocker):
        default_mapping = MagicMock()
        one = mocker.patch(
            "services.gl_account_resolver._one_or_error",
            side_effect=[None, default_mapping],
        )
        result = _find_active_mapping(1, "CASH", branch_id=5)
        assert result is default_mapping
        assert one.call_count == 2


class TestRaiseMissingOrInactive:
    @staticmethod
    def _inactive_mapping(db_session, sample_tenant, sample_branch, branch_id):
        from models.gl import GLAccount, GLAccountMapping
        from models._constants import GL_CONCEPT_CASH

        account = GLAccount.query.filter_by(
            tenant_id=sample_tenant.id, code="1111"
        ).first()
        if account is None:
            account = GLAccount(
                tenant_id=sample_tenant.id,
                code="1111",
                name="Cash",
                type="asset",
                is_active=True,
            )
            db_session.add(account)
            db_session.flush()
        mapping = GLAccountMapping(
            tenant_id=sample_tenant.id,
            concept_code=GL_CONCEPT_CASH,
            gl_account_id=account.id,
            branch_id=branch_id,
            is_active=False,
        )
        db_session.add(mapping)
        db_session.commit()
        return GL_CONCEPT_CASH

    def test_inactive_branch_override(
        self, app, db_session, sample_tenant, sample_branch, sample_gl_accounts
    ):
        from models._constants import GL_CONCEPT_CASH

        with app.app_context():
            self._inactive_mapping(
                db_session, sample_tenant, sample_branch, sample_branch.id
            )
            with pytest.raises(
                GLMappingError, match="Branch override mapping exists but is inactive"
            ):
                _raise_missing_or_inactive_mapping(
                    sample_tenant.id, GL_CONCEPT_CASH, sample_branch.id
                )

    def test_inactive_tenant_default(
        self, app, db_session, sample_tenant, sample_gl_accounts
    ):
        from models._constants import GL_CONCEPT_CASH

        with app.app_context():
            self._inactive_mapping(db_session, sample_tenant, None, None)
            with pytest.raises(
                GLMappingError, match="Tenant-level mapping exists but is inactive"
            ):
                _raise_missing_or_inactive_mapping(
                    sample_tenant.id, GL_CONCEPT_CASH, None
                )

    def test_no_mapping_raises(self, app, sample_tenant):
        with app.app_context():
            with pytest.raises(GLMappingError, match="No active GL account mapping"):
                _raise_missing_or_inactive_mapping(sample_tenant.id, "CASH", None)


class TestValidatedAccount:
    @staticmethod
    def _mapping(**kwargs):
        defaults = dict(
            branch_id=None,
            branch=None,
            gl_account=SimpleNamespace(
                tenant_id=1,
                is_active=True,
                is_header=False,
            ),
        )
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_missing_branch_raises(self):
        mapping = self._mapping(branch_id=2, branch=None)
        with pytest.raises(GLMappingError, match="missing branch"):
            _validated_account(mapping, 1, "CASH", 2)

    def test_branch_wrong_tenant_raises(self):
        branch = SimpleNamespace(tenant_id=99)
        mapping = self._mapping(branch_id=2, branch=branch)
        with pytest.raises(GLMappingError, match="different tenant"):
            _validated_account(mapping, 1, "CASH", 2)

    def test_missing_account_raises(self):
        mapping = self._mapping(gl_account=None)
        with pytest.raises(GLMappingError, match="does not exist"):
            _validated_account(mapping, 1, "CASH", None)

    def test_account_wrong_tenant_raises(self):
        account = SimpleNamespace(tenant_id=99, is_active=True, is_header=False)
        mapping = self._mapping(gl_account=account)
        with pytest.raises(GLMappingError, match="belongs to a different tenant"):
            _validated_account(mapping, 1, "CASH", None)

    def test_inactive_account_raises(self):
        account = SimpleNamespace(tenant_id=1, is_active=False, is_header=False)
        mapping = self._mapping(gl_account=account)
        with pytest.raises(GLMappingError, match="inactive"):
            _validated_account(mapping, 1, "CASH", None)

    def test_header_account_raises(self):
        account = SimpleNamespace(tenant_id=1, is_active=True, is_header=True)
        mapping = self._mapping(gl_account=account)
        with pytest.raises(GLMappingError, match="header"):
            _validated_account(mapping, 1, "CASH", None)

    def test_valid_account_returns(self):
        account = SimpleNamespace(tenant_id=1, is_active=True, is_header=False)
        mapping = self._mapping(gl_account=account)
        assert _validated_account(mapping, 1, "CASH", None) is account


class TestResolveDynamic:
    def test_resolve_success(self, app, mocker):
        account = SimpleNamespace(tenant_id=1, is_active=True, is_header=False)
        mapping = SimpleNamespace(branch_id=None, branch=None, gl_account=account)
        mocker.patch(
            "services.gl_account_resolver.is_dynamic_gl_mapping_enabled",
            return_value=True,
        )
        mocker.patch(
            "services.gl_account_resolver._find_active_mapping",
            return_value=mapping,
        )
        with app.app_context():
            assert resolve_gl_account(1, GL_CONCEPT_CASH) is account

    def test_resolve_missing_mapping(self, app, mocker):
        mocker.patch(
            "services.gl_account_resolver.is_dynamic_gl_mapping_enabled",
            return_value=True,
        )
        mocker.patch(
            "services.gl_account_resolver._find_active_mapping",
            return_value=None,
        )
        mocker.patch(
            "services.gl_account_resolver._raise_missing_or_inactive_mapping",
            side_effect=GLMappingError(1, "CASH", None, "missing"),
        )
        with app.app_context():
            with pytest.raises(GLMappingError):
                resolve_gl_account(1, GL_CONCEPT_CASH)
