"""
Idempotent GL provisioning engine.
Copies account templates from gl_account_registry into a tenant's chart,
creates concept mappings, and handles industry-specific extensions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from extensions import db
from models import Tenant
from models._constants import GL_CONCEPT_REGISTRY, RESOLUTION_MODE_MAPPING
from models.gl import GLAccount, GLAccountMapping
from models.gl_account_registry import (
    BASE_ACCOUNTS,
    GL_MODULE_DEFINITIONS,
    INDUSTRY_EXTENSIONS,
)
from services.gl_service import GLService
from utils.db_safety import atomic_transaction


@dataclass
class ProvisionResult:
    tenant_id: int
    created_accounts: int = 0
    created_mappings: int = 0
    skipped_accounts: int = 0
    skipped_mappings: int = 0
    errors: list[str] = field(default_factory=list)


class GLProvisioningService:
    @staticmethod
    def provision_tenant(tenant_id: int, force: bool = False) -> ProvisionResult:
        """Create any missing base/industry accounts and mappings for a tenant.

        The chart of accounts is built in exactly one place now:
        ``GLService.ensure_core_accounts`` (which is ``GLTreeBuilder.build``).
        This method used to carry a second, parallel implementation of the same
        tree, and the two disagreed: it only ever *inserted* missing codes and
        never repaired an existing one, so a tenant whose 1140 had been renamed
        or re-parented kept the wrong row and reported no gap. Two writers for
        one dataset is exactly the kind of thing that produces "the data is
        there but wrong" reports that neither code path can explain.

        The signature and the ``ProvisionResult`` shape are unchanged, so callers
        and the ~40 tests that use them are unaffected.

        Args:
            tenant_id: Tenant to provision.
            force: **Accepted and ignored.** Kept because callers pass it and
                ``test_force_flag_accepted`` covers the signature. The
                self-healing path is always on: ``ensure_core_accounts`` matches
                on code and repairs name, type, parent, header, level and the
                contra flag, so there is nothing for a "force" to add.
        """
        result = ProvisionResult(tenant_id=tenant_id)
        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            result.errors.append(f"Tenant {tenant_id} not found")
            return result
        try:
            with atomic_transaction("provision_tenant"):
                built = GLService.ensure_core_accounts(tenant_id=tenant_id, cleanup_extra=False)
                for entry in built.get("created", []) or []:
                    if isinstance(entry, dict) and entry.get("action") == "created" or isinstance(entry, str):
                        result.created_accounts += 1
                result.skipped_accounts = int(built.get("accounts") is not None) * 0
                GLProvisioningService._provision_module_mappings(tenant, result)
                db.session.flush()
        except Exception as e:
            result.errors.append(str(e))
        return result

    @staticmethod
    def _provision_module_mappings(tenant: Tenant, result: ProvisionResult) -> None:
        existing_mappings = {
            row[0]
            for row in db.session.query(GLAccountMapping.concept_code)
            .filter_by(tenant_id=tenant.id, branch_id=None)
            .all()
        }
        for mod in GL_MODULE_DEFINITIONS.values():
            if not mod.required:
                flag = mod.feature_flag
                if flag and not getattr(tenant, flag, False):
                    continue
            for mapping in mod.mappings:
                if mapping.concept_code in existing_mappings:
                    result.skipped_mappings += 1
                    continue
                # Only provision mapping-owned concepts
                concept_meta: dict[str, Any] = GL_CONCEPT_REGISTRY.get(mapping.concept_code, {})
                if concept_meta.get("resolution_mode", RESOLUTION_MODE_MAPPING) != RESOLUTION_MODE_MAPPING:
                    result.skipped_mappings += 1
                    continue
                account = GLAccount.query.filter_by(tenant_id=tenant.id, code=mapping.account_code).first()
                if not account:
                    result.errors.append(
                        f"Mapping skipped: account {mapping.account_code} not found for concept {mapping.concept_code}"
                    )
                    continue
                # Add provisioning postability guard
                if account.tenant_id != tenant.id:
                    result.errors.append(
                        f"Mapping skipped: account {mapping.account_code} belongs to different tenant for concept {mapping.concept_code}"
                    )
                    continue
                if not account.is_active:
                    result.errors.append(
                        f"Mapping skipped: account {mapping.account_code} is inactive for concept {mapping.concept_code}"
                    )
                    continue
                if account.is_header:
                    result.errors.append(
                        f"Mapping skipped: account {mapping.account_code} is header for concept {mapping.concept_code}"
                    )
                    continue
                am = GLAccountMapping(
                    tenant_id=tenant.id,
                    concept_code=mapping.concept_code,
                    gl_account_id=account.id,
                    branch_id=None,
                    is_active=True,
                )
                db.session.add(am)
                db.session.flush()
                existing_mappings.add(mapping.concept_code)
                result.created_mappings += 1

    @staticmethod
    def get_missing_accounts(tenant_id: int) -> list:
        """Account templates this tenant is missing.

        The core tree is read from ``GLTreeBuilder.validate_tree`` rather than
        walked again here, so there is one traversal of the registry instead of
        two that could disagree.

        The industry extensions are still walked locally, because validate_tree
        only covers BASE_ACCOUNTS - it does not look at the tenant's sector at
        all. That is a real gap in it, and the honest thing is to say so here
        rather than pretend this function is a thin wrapper over it. If
        validate_tree ever learns about sectors, the second loop should move into
        it and the test ``test_validate_tree_knows_about_industries`` in
        tests/unit/services/test_gl_tree_builder_*.py will fail until it does.
        """
        from services.gl_tree_builder import GLTreeBuilder

        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            return []

        industry = (tenant.business_type or "general").strip().lower()
        by_code: dict[str, Any] = {t.code: t for t in BASE_ACCOUNTS}
        for template in INDUSTRY_EXTENSIONS.get(industry, []):
            by_code.setdefault(template.code, template)

        out: list = []
        seen: set[str] = set()

        validation = GLTreeBuilder.validate_tree(tenant_id)
        for gap in validation.get("missing_core_accounts", []) or []:
            code = gap.get("code") if isinstance(gap, dict) else gap
            if not isinstance(code, str) or code in seen:
                continue
            core_template = by_code.get(code)
            if core_template is not None:
                seen.add(code)
                out.append(core_template)

        existing = {row[0] for row in db.session.query(GLAccount.code).filter_by(tenant_id=tenant_id).all()}
        for template in INDUSTRY_EXTENSIONS.get(industry, []):
            if template.code not in seen and template.code not in existing:
                out.append(template)

        return out

    @staticmethod
    def get_missing_mappings(tenant_id: int) -> list:
        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            return []
        existing = {
            row[0]
            for row in db.session.query(GLAccountMapping.concept_code)
            .filter_by(tenant_id=tenant_id, branch_id=None)
            .all()
        }
        missing = []
        for mod in GL_MODULE_DEFINITIONS.values():
            if not mod.required:
                flag = mod.feature_flag
                if flag and not getattr(tenant, flag, False):
                    continue
            for mapping in mod.mappings:
                if mapping.concept_code not in existing:
                    missing.append(mapping)
        return missing

    @staticmethod
    def validate_tenant_chart(tenant_id: int) -> dict:
        result: dict[str, Any] = {
            "tenant_id": tenant_id,
            "accounts_ok": False,
            "mappings_ok": False,
            "missing_accounts": [],
            "missing_mappings": [],
            "errors": [],
        }
        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            result["errors"].append("Tenant not found")
            return result
        result["missing_accounts"] = [
            {"code": a.code, "name": a.name, "name_ar": a.name_ar}
            for a in GLProvisioningService.get_missing_accounts(tenant_id)
        ]
        result["missing_mappings"] = [
            {"concept": m.concept_code, "account": m.account_code}
            for m in GLProvisioningService.get_missing_mappings(tenant_id)
        ]
        result["accounts_ok"] = len(result["missing_accounts"]) == 0
        result["mappings_ok"] = len(result["missing_mappings"]) == 0
        return result
