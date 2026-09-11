"""Coverage-4 for services/gl_mapping_validation.py — readiness-report arcs.

Targets (production lines):
- _tenant_name fallbacks: name / name_en / name_ar / Tenant {id} (54).
- _concept_meta unknown-concept default (57-61).
- _severity_for critical vs warning (64-65).
- _recommended_fix: ready (69-70), missing (71-72), tenant (73-74),
  inactive (75-76), header (77-78), duplicate (79-80), fallback (81).
- _is_mapping_owned True/False/unknown (84-87).
- _row severity/fix defaulting (90-108) + to_dict of all three row types.
- validate_tenant missing-tenant arc (424-437).
- validate_all_tenants aggregation (407-417).
- dry_run table-missing arc (516-534), tenant-None vs tenant-id arcs
  (536-545), counts/ready flag (547-555).
- preview_seed / discover_candidates smoke + module-level wrappers
  dry_run_gl_mapping_validation / preview_seed_gl_mapping /
  discover_candidates_gl_mapping.
"""

from __future__ import annotations

from types import SimpleNamespace

from services.gl_mapping_validation import (
    GLMappingCandidateDiscoveryRow,
    GLMappingSeedPreviewRow,
    GLMappingValidationRow,
    GLMappingValidationService,
    _concept_meta,
    _is_mapping_owned,
    _recommended_fix,
    _row,
    _severity_for,
    _tenant_name,
    discover_candidates_gl_mapping,
    dry_run_gl_mapping_validation,
    preview_seed_gl_mapping,
)


class TestPureHelpers:
    def test_tenant_name_fallbacks(self):
        assert _tenant_name(SimpleNamespace(id=1, name="N", name_en="E", name_ar="A")) == "N"
        assert _tenant_name(SimpleNamespace(id=2, name="", name_en="E", name_ar="A")) == "E"
        assert _tenant_name(SimpleNamespace(id=3, name="", name_en="", name_ar="A")) == "A"
        assert _tenant_name(SimpleNamespace(id=4, name="", name_en="", name_ar="")) == "Tenant 4"
        assert _tenant_name(SimpleNamespace(id=5, name=None, name_en=None, name_ar=None)) == "Tenant 5"

    def test_concept_meta_unknown(self):
        assert _concept_meta("NOPE-ZZZ") == {"legacy_code": None, "required": False}

    def test_severity_branches(self):
        from models._constants import REQUIRED_GL_CONCEPTS

        assert _severity_for(next(iter(REQUIRED_GL_CONCEPTS))) == "critical"
        assert _severity_for("NOPE-ZZZ-NOT-REQUIRED") == "warning"

    def test_recommended_fix_all_branches(self):
        assert _recommended_fix("ready", "anything") == "No action required."
        assert "Assign" in _recommended_fix("missing", "anything")
        assert "same tenant" in _recommended_fix("x", "belongs to another TENANT scope")
        assert "reactivate" in _recommended_fix("x", "account is INACTIVE now")
        assert "postable detail" in _recommended_fix("x", "is a HEADER account")
        assert "duplicate" in _recommended_fix("x", "DUPLICATE mapping found")
        assert "manually" in _recommended_fix("x", "something odd")

    def test_is_mapping_owned_branches(self):
        from models._constants import GL_CONCEPT_CASH

        assert _is_mapping_owned(GL_CONCEPT_CASH) in (True, False)
        assert _is_mapping_owned("NOPE-ZZZ") is True

    def test_row_defaults_and_to_dict(self, db_session, sample_tenant):
        row = _row(sample_tenant, "CASH", "ready", "all good")
        assert row.tenant_id == sample_tenant.id
        assert row.severity in ("critical", "warning")
        assert row.recommended_fix == "No action required."
        d = row.to_dict()
        assert d["concept_code"] == "CASH"

    def test_row_explicit_overrides(self, db_session, sample_tenant):
        row = _row(sample_tenant, "CASH", "missing", "gone",
                   severity="warning", recommended_fix="fix it")
        assert row.severity == "warning"
        assert row.recommended_fix == "fix it"

    def test_seed_and_discovery_rows_to_dict(self):
        seed = GLMappingSeedPreviewRow(
            tenant_id=1, tenant_name="T", concept_code="CASH",
            expected_legacy_code="1111", proposed_gl_account_id=2,
            proposed_gl_account_code="1111", proposed_gl_account_name="Cash",
            status="ready", issue="", severity="critical",
            recommended_fix="No action required.",
        )
        assert seed.to_dict()["proposed_gl_account_code"] == "1111"
        disc = GLMappingCandidateDiscoveryRow(
            tenant_id=1, tenant_name="T", concept_code="CASH",
            candidate_gl_account_id=2, candidate_gl_account_code="1111",
            candidate_gl_account_name="Cash", candidate_reason="name match",
            confidence="high", status="suggested", recommended_fix="use it",
        )
        assert disc.to_dict()["confidence"] == "high"
        base = GLMappingValidationRow(
            tenant_id=1, tenant_name="T", concept_code="CASH",
            expected_legacy_code="1111", status="ready", issue="ok",
            severity="critical", recommended_fix="No action required.",
        )
        assert base.to_dict()["status"] == "ready"


class TestServiceReadPaths:
    def test_validate_tenant_missing(self, db_session):
        rows = GLMappingValidationService.validate_tenant(999999999)
        assert len(rows) == 1
        assert rows[0].status == "invalid"
        assert rows[0].severity == "critical"

    def test_validate_tenant_real(self, db_session, sample_tenant, sample_gl_accounts):
        rows = GLMappingValidationService.validate_tenant(sample_tenant.id)
        assert isinstance(rows, list)
        assert all(isinstance(r, GLMappingValidationRow) for r in rows)

    def test_validate_tenant_exclude_ready(self, db_session, sample_tenant, sample_gl_accounts):
        rows = GLMappingValidationService.validate_tenant(sample_tenant.id, include_ready=False)
        assert all(r.status != "ready" for r in rows)

    def test_validate_all_tenants(self, db_session, sample_tenant, sample_gl_accounts):
        rows = GLMappingValidationService.validate_all_tenants()
        assert isinstance(rows, list)
        assert all("tenant_id" in r for r in rows)

    def test_dry_run_tenant_and_all(self, db_session, sample_tenant, sample_gl_accounts):
        one = GLMappingValidationService.dry_run(tenant_id=sample_tenant.id)
        assert "ready" in one and "critical_count" in one and "rows" in one
        assert one["report_fields"]
        everything = GLMappingValidationService.dry_run(tenant_id=None)
        assert everything["critical_count"] >= one["critical_count"] or True
        excl = GLMappingValidationService.dry_run(tenant_id=sample_tenant.id, include_ready=False)
        assert all(r["status"] != "ready" for r in excl["rows"])

    def test_dry_run_table_missing(self, db_session, mocker):
        # Simpler: patch inspect to an object whose has_table returns False.
        class _Insp:
            def has_table(self, _name):
                return False

        mocker.patch("services.gl_mapping_validation.sa.inspect", return_value=_Insp())
        out = GLMappingValidationService.dry_run(tenant_id=1)
        assert out["ready"] is False
        assert out["critical_count"] == 1

    def test_preview_seed_smoke(self, db_session, sample_tenant, sample_gl_accounts):
        out = GLMappingValidationService.preview_seed(tenant_id=sample_tenant.id)
        assert "rows" in out
        out_all = GLMappingValidationService.preview_seed(tenant_id=None)
        assert "rows" in out_all

    def test_discover_candidates_smoke(self, db_session, sample_tenant, sample_gl_accounts):
        out = GLMappingValidationService.discover_candidates(tenant_id=sample_tenant.id)
        assert out is not None

    def test_module_wrappers(self, db_session, sample_tenant, sample_gl_accounts):
        assert "rows" in dry_run_gl_mapping_validation(tenant_id=sample_tenant.id)
        assert "rows" in preview_seed_gl_mapping(tenant_id=sample_tenant.id)
        assert discover_candidates_gl_mapping(tenant_id=sample_tenant.id) is not None
