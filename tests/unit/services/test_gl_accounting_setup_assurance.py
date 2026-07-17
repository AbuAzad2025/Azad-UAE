"""GL accounting setup — tenant onboarding plan/execute/validate."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.gl_accounting_setup import (
    ConceptSetupRule,
    GLAccountingSetupService,
    SetupPlanAction,
)


def _tenant(tid=1, name="Test Co"):
    return SimpleNamespace(id=tid, name=name)


def _account(
    aid=10,
    code="1130",
    name="AR",
    name_ar="",
    acc_type="asset",
    active=True,
    header=False,
):
    acc = SimpleNamespace(
        id=aid,
        code=code,
        name=name,
        name_ar=name_ar,
        type=acc_type,
        is_active=active,
        is_header=header,
        level=1,
        children=[],
    )
    return acc


class TestPlan:
    def test_plan_missing_tenant(self, mocker):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch("services.gl_accounting_setup.Tenant.query", mock_q)
        assert GLAccountingSetupService.plan(999) is None

    def test_plan_returns_actions(self, mocker):
        tenant = _tenant()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = tenant
        mocker.patch("services.gl_accounting_setup.Tenant.query", mock_q)
        mocker.patch.object(
            GLAccountingSetupService,
            "_build_plan",
            return_value=[
                SetupPlanAction(
                    "map_concept", 1, "AR", gl_account_id=5, gl_account_code="1130"
                ),
            ],
        )
        plan = GLAccountingSetupService.plan(1)
        assert plan is not None
        assert plan.tenant_id == 1
        assert len(plan.actions) == 1

    def test_plan_all(self, mocker):
        mock_q = MagicMock()
        mock_q.order_by.return_value.all.return_value = [_tenant()]
        mocker.patch("services.gl_accounting_setup.Tenant.query", mock_q)
        mocker.patch.object(GLAccountingSetupService, "_build_plan", return_value=[])
        plans = GLAccountingSetupService.plan_all()
        assert len(plans) == 1


class TestExecute:
    def test_execute_tenant_not_found(self, mocker):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch("services.gl_accounting_setup.Tenant.query", mock_q)
        result = GLAccountingSetupService.execute(99, dry_run=True)
        assert "not found" in result.errors[0]

    def test_execute_dry_run_rolls_back(self, mocker):
        tenant = _tenant()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = tenant
        mocker.patch("services.gl_accounting_setup.Tenant.query", mock_q)
        mocker.patch.object(
            GLAccountingSetupService,
            "_build_plan",
            side_effect=[
                [SetupPlanAction("create_account", 1, "CASH")],
                [
                    SetupPlanAction(
                        "map_concept",
                        1,
                        "CASH",
                        gl_account_id=7,
                        gl_account_code="1110-B1",
                    )
                ],
            ],
        )
        mocker.patch.object(
            GLAccountingSetupService,
            "_create_account",
            return_value=_account(7, "1110-B1"),
        )
        mock_session = mocker.patch("services.gl_accounting_setup.db.session")
        mock_mapping_q = MagicMock()
        mock_mapping_q.filter_by.return_value.first.return_value = None
        mocker.patch(
            "services.gl_accounting_setup.GLAccountMapping.query", mock_mapping_q
        )
        result = GLAccountingSetupService.execute(1, dry_run=True)
        mock_session.rollback.assert_called_once()
        assert len(result.created_accounts) == 1

    def test_execute_create_account_error(self, mocker):
        tenant = _tenant()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = tenant
        mocker.patch("services.gl_accounting_setup.Tenant.query", mock_q)
        mocker.patch.object(
            GLAccountingSetupService,
            "_build_plan",
            return_value=[
                SetupPlanAction("create_account", 1, "CASH"),
            ],
        )
        mocker.patch.object(
            GLAccountingSetupService,
            "_create_account",
            side_effect=RuntimeError("dup code"),
        )
        mocker.patch("services.gl_accounting_setup.db.session")
        result = GLAccountingSetupService.execute(1, dry_run=False)
        assert any("Create account failed" in e for e in result.errors)

    def test_execute_skips_existing_mapping(self, mocker):
        tenant = _tenant()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = tenant
        mocker.patch("services.gl_accounting_setup.Tenant.query", mock_q)
        mocker.patch.object(
            GLAccountingSetupService,
            "_build_plan",
            return_value=[
                SetupPlanAction(
                    "map_concept", 1, "AR", gl_account_id=5, gl_account_code="1130"
                ),
            ],
        )
        mock_mapping_q = MagicMock()
        mock_mapping_q.filter_by.return_value.first.return_value = MagicMock()
        mocker.patch(
            "services.gl_accounting_setup.GLAccountMapping.query", mock_mapping_q
        )
        mocker.patch("services.gl_accounting_setup.db.session")
        result = GLAccountingSetupService.execute(1, dry_run=False)
        assert result.created_mappings == []

    def test_execute_map_concept_error(self, mocker):
        tenant = _tenant()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = tenant
        mocker.patch("services.gl_accounting_setup.Tenant.query", mock_q)
        mocker.patch.object(
            GLAccountingSetupService,
            "_build_plan",
            return_value=[
                SetupPlanAction(
                    "map_concept", 1, "AR", gl_account_id=5, gl_account_code="1130"
                ),
            ],
        )
        mock_mapping_q = MagicMock()
        mock_mapping_q.filter_by.return_value.first.return_value = None
        mapping_cls = MagicMock(side_effect=RuntimeError("fail"))
        mapping_cls.query = mock_mapping_q
        mocker.patch("services.gl_accounting_setup.GLAccountMapping", mapping_cls)
        mocker.patch("services.gl_accounting_setup.db.session")
        result = GLAccountingSetupService.execute(1, dry_run=True)
        assert any("Map concept failed" in e for e in result.errors)

    def test_execute_all(self, mocker):
        mock_q = MagicMock()
        mock_q.order_by.return_value.all.return_value = [_tenant()]
        mocker.patch("services.gl_accounting_setup.Tenant.query", mock_q)
        mocker.patch.object(
            GLAccountingSetupService, "execute", return_value=MagicMock()
        )
        assert len(GLAccountingSetupService.execute_all()) == 1


class TestValidate:
    def test_delegates_to_dry_run(self, mocker):
        mocker.patch(
            "services.gl_mapping_validation.dry_run_gl_mapping_validation",
            return_value={"ready": True},
        )
        result = GLAccountingSetupService.validate(tenant_id=1)
        assert result["ready"] is True


class TestFindBestCandidate:
    def test_legacy_code_match(self, mocker):
        acc = _account(code="1130")
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = acc
        mocker.patch("services.gl_accounting_setup.GLAccount.query", mock_q)
        rule = ConceptSetupRule(legacy_code="1130", expected_types=("asset",))
        found = GLAccountingSetupService._find_best_candidate(_tenant(), rule)
        assert found is acc

    def test_name_search_english(self, mocker):
        acc = _account(code="1110-B1", name="Main Cashbox")
        mock_q = MagicMock()
        mock_q.filter_by.return_value.all.return_value = [acc]
        mocker.patch("services.gl_accounting_setup.GLAccount.query", mock_q)
        rule = ConceptSetupRule(search_names=("cash",), expected_types=("asset",))
        assert GLAccountingSetupService._find_best_candidate(_tenant(), rule) is acc

    def test_name_search_arabic(self, mocker):
        acc = _account(code="1120-B1", name="X", name_ar="حساب بنك")
        mock_q = MagicMock()
        mock_q.filter_by.return_value.all.return_value = [acc]
        mocker.patch("services.gl_accounting_setup.GLAccount.query", mock_q)
        rule = ConceptSetupRule(search_names=("بنك",), expected_types=("asset",))
        assert GLAccountingSetupService._find_best_candidate(_tenant(), rule) is acc

    def test_parent_child_scan_prefers_main(self, mocker):
        parent = _account(code="1110", header=True)
        child = _account(code="1110-B1", name="Primary Cash")
        child.is_header = False
        parent.children = [child]
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = parent
        mocker.patch("services.gl_accounting_setup.GLAccount.query", mock_q)
        rule = ConceptSetupRule(
            parent_code_hint="1110",
            expected_types=("asset",),
            creation_template={"code_suffix": "-B1", "name": "Cash", "type": "asset"},
        )
        assert GLAccountingSetupService._find_best_candidate(_tenant(), rule) is child


class TestBuildPlan:
    def test_alias_resolution(self, mocker):
        cogs = _account(20, "5100", "COGS", acc_type="expense")

        def fake_find(tenant, rule):
            if rule.legacy_code == "5100":
                return cogs
            return None

        mocker.patch.object(
            GLAccountingSetupService, "_find_best_candidate", side_effect=fake_find
        )
        actions = GLAccountingSetupService._build_plan(_tenant())
        alias_actions = [a for a in actions if a.concept_code == "COGS_REVERSAL"]
        assert alias_actions and alias_actions[0].action_type == "map_concept"

    def test_skip_when_no_template(self, mocker):
        mocker.patch.object(
            GLAccountingSetupService, "_find_best_candidate", return_value=None
        )
        actions = GLAccountingSetupService._build_plan(_tenant())
        skips = [a for a in actions if a.action_type == "skip"]
        assert skips


class TestCreateAccount:
    def test_code_suffix_strategy(self, mocker):
        parent = SimpleNamespace(id=5, level=1)
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = parent
        mocker.patch("services.gl_accounting_setup.GLAccount.query", mock_q)
        mocker.patch.object(
            GLAccountingSetupService, "_next_child_code", return_value="1110-B2"
        )
        acc = GLAccountingSetupService._create_account(_tenant(), "CASH")
        assert acc.code == "1110-B2"
        assert acc.liquidity_kind == "cash"

    def test_code_near_strategy(self, mocker):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch("services.gl_accounting_setup.GLAccount.query", mock_q)
        mocker.patch.object(
            GLAccountingSetupService, "_next_available_code", return_value="4110"
        )
        acc = GLAccountingSetupService._create_account(_tenant(), "SALES_RETURNS")
        assert acc.code == "4110"

    def test_no_code_strategy_raises(self, mocker):
        mocker.patch.dict(
            "services.gl_accounting_setup.DEFAULT_CONCEPT_RULES",
            {"BAD": ConceptSetupRule()},
        )
        with pytest.raises(ValueError, match="No code strategy"):
            GLAccountingSetupService._create_account(_tenant(), "BAD")


class TestCodeAllocation:
    def test_next_child_code(self, mocker):
        existing = [_account(code="1120-B1"), _account(code="1120-B2")]
        mock_q = MagicMock()
        mock_q.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = (
            existing
        )
        mocker.patch("services.gl_accounting_setup.GLAccount.query", mock_q)
        assert GLAccountingSetupService._next_child_code(1, "1120") == "1120-B3"

    def test_next_child_code_skips_invalid_suffix(self, mocker):
        existing = [_account(code="1120-BX")]
        mock_q = MagicMock()
        mock_q.filter_by.return_value.filter.return_value.order_by.return_value.all.return_value = (
            existing
        )
        mocker.patch("services.gl_accounting_setup.GLAccount.query", mock_q)
        assert GLAccountingSetupService._next_child_code(1, "1120") == "1120-B1"

    def test_next_available_code_base_free(self, mocker):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch("services.gl_accounting_setup.GLAccount.query", mock_q)
        assert GLAccountingSetupService._next_available_code(1, "4110") == "4110"

    def test_next_available_code_increments(self, mocker):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.side_effect = [MagicMock(), None]
        mocker.patch("services.gl_accounting_setup.GLAccount.query", mock_q)
        assert GLAccountingSetupService._next_available_code(1, "4110") == "4111"

    def test_next_available_code_exhausted(self, mocker):
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = MagicMock()
        mocker.patch("services.gl_accounting_setup.GLAccount.query", mock_q)
        with pytest.raises(RuntimeError, match="No available code"):
            GLAccountingSetupService._next_available_code(1, "4110")


class TestSetupPlanAction:
    def test_to_dict(self):
        action = SetupPlanAction(
            "map_concept", 1, "AR", gl_account_id=5, gl_account_code="1130"
        )
        assert action.to_dict()["concept_code"] == "AR"


class TestSetupPlan:
    def test_to_dict(self):
        from services.gl_accounting_setup import SetupPlan

        plan = SetupPlan(1, "Co", [SetupPlanAction("skip", 1, "X")])
        d = plan.to_dict()
        assert d["tenant_id"] == 1
        assert len(d["actions"]) == 1


class TestSetupResult:
    def test_to_dict(self):
        from services.gl_accounting_setup import SetupResult

        result = SetupResult(1, "Co", [], [], [], [])
        assert result.to_dict()["tenant_name"] == "Co"


class TestExecuteCommit:
    def test_execute_commits_when_not_dry_run(self, mocker):
        tenant = _tenant()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = tenant
        mocker.patch("services.gl_accounting_setup.Tenant.query", mock_q)
        mocker.patch.object(GLAccountingSetupService, "_build_plan", return_value=[])
        mock_session = mocker.patch("services.gl_accounting_setup.db.session")
        GLAccountingSetupService.execute(1, dry_run=False)
        mock_session.flush.assert_called_once()

    def test_execute_commit_failure_reraises(self, mocker):
        tenant = _tenant()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = tenant
        mocker.patch("services.gl_accounting_setup.Tenant.query", mock_q)
        mocker.patch.object(GLAccountingSetupService, "_build_plan", return_value=[])
        mock_session = mocker.patch("services.gl_accounting_setup.db.session")
        mock_session.flush.side_effect = RuntimeError("commit fail")
        with pytest.raises(RuntimeError, match="commit fail"):
            GLAccountingSetupService.execute(1, dry_run=False)
        mock_session.rollback.assert_called_once()

    def test_execute_creates_and_maps_not_dry_run(self, mocker):
        tenant = _tenant()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = tenant
        mocker.patch("services.gl_accounting_setup.Tenant.query", mock_q)
        mocker.patch.object(
            GLAccountingSetupService,
            "_build_plan",
            side_effect=[
                [SetupPlanAction("create_account", 1, "CASH")],
                [
                    SetupPlanAction(
                        "map_concept",
                        1,
                        "CASH",
                        gl_account_id=7,
                        gl_account_code="1110-B1",
                    )
                ],
            ],
        )
        acct = _account(7, "1110-B1")
        mocker.patch.object(
            GLAccountingSetupService, "_create_account", return_value=acct
        )
        mock_session = mocker.patch("services.gl_accounting_setup.db.session")
        mock_mapping_q = MagicMock()
        mock_mapping_q.filter_by.return_value.first.return_value = None
        mapping_cls = MagicMock()
        mapping_cls.query = mock_mapping_q
        mocker.patch("services.gl_accounting_setup.GLAccountMapping", mapping_cls)
        GLAccountingSetupService.execute(1, dry_run=False)
        assert mock_session.flush.call_count >= 2

    def test_skips_map_without_account_id(self, mocker):
        tenant = _tenant()
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = tenant
        mocker.patch("services.gl_accounting_setup.Tenant.query", mock_q)
        mocker.patch.object(
            GLAccountingSetupService,
            "_build_plan",
            return_value=[
                SetupPlanAction(
                    "map_concept", 1, "AR", gl_account_id=None, reason="missing"
                ),
            ],
        )
        mocker.patch("services.gl_accounting_setup.db.session")
        result = GLAccountingSetupService.execute(1, dry_run=True)
        assert result.skipped_concepts[0]["concept_code"] == "AR"


class TestFindBestCandidateEdge:
    def test_legacy_inactive_skipped(self, mocker):
        acc = _account(code="1130", active=False)
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = acc
        mocker.patch("services.gl_accounting_setup.GLAccount.query", mock_q)
        rule = ConceptSetupRule(legacy_code="1130", expected_types=("asset",))
        assert GLAccountingSetupService._find_best_candidate(_tenant(), rule) is None

    def test_wrong_type_skipped(self, mocker):
        acc = _account(code="1130", acc_type="liability")
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = acc
        mocker.patch("services.gl_accounting_setup.GLAccount.query", mock_q)
        rule = ConceptSetupRule(legacy_code="1130", expected_types=("asset",))
        assert GLAccountingSetupService._find_best_candidate(_tenant(), rule) is None

    def test_name_search_skips_wrong_type(self, mocker):
        acc = _account(code="5100", name="Cash", acc_type="expense")
        mock_q = MagicMock()
        mock_q.filter_by.return_value.all.return_value = [acc]
        mocker.patch("services.gl_accounting_setup.GLAccount.query", mock_q)
        rule = ConceptSetupRule(search_names=("cash",), expected_types=("asset",))
        assert GLAccountingSetupService._find_best_candidate(_tenant(), rule) is None

    def test_parent_returns_first_sorted_child(self, mocker):
        parent = _account(code="1110", header=True)
        child1 = _account(code="1110-B2", name="Secondary Cash")
        child1.is_header = False
        child2 = _account(code="1110-B1", name="Other Cash")
        child2.is_header = False
        parent.children = [child1, child2]
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = parent
        mocker.patch("services.gl_accounting_setup.GLAccount.query", mock_q)
        rule = ConceptSetupRule(parent_code_hint="1110", expected_types=("asset",))
        assert (
            GLAccountingSetupService._find_best_candidate(_tenant(), rule).code
            == "1110-B1"
        )
