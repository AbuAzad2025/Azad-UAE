"""
Idempotent GL provisioning engine.
Copies account templates from gl_account_registry into a tenant's chart,
creates concept mappings, and handles industry-specific extensions.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from extensions import db
from models import Tenant
from models.gl import GLAccount, GLAccountMapping
from models._constants import GL_CONCEPT_REGISTRY, RESOLUTION_MODE_MAPPING
from models.gl_account_registry import (
    BASE_ACCOUNTS,
    INDUSTRY_EXTENSIONS,
    GL_MODULE_DEFINITIONS,
    VALID_INDUSTRY_CODES,
)


@dataclass
class ProvisionResult:
    tenant_id: int
    created_accounts: int = 0
    created_mappings: int = 0
    skipped_accounts: int = 0
    skipped_mappings: int = 0
    errors: list = None
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class GLProvisioningService:
    @staticmethod
    def provision_tenant(tenant_id: int, force: bool = False) -> ProvisionResult:
        result = ProvisionResult(tenant_id=tenant_id)
        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            result.errors.append(f"Tenant {tenant_id} not found")
            return result
        try:
            GLProvisioningService._provision_base_accounts(tenant, result)
            GLProvisioningService._provision_industry_accounts(tenant, result)
            GLProvisioningService._provision_module_mappings(tenant, result)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            result.errors.append(str(e))
        return result
    @staticmethod
    def _provision_base_accounts(tenant: Tenant, result: ProvisionResult) -> None:
        existing_codes = {
            row[0] for row in
            db.session.query(GLAccount.code).filter_by(tenant_id=tenant.id).all()
        }
        sorted_accounts = sorted(BASE_ACCOUNTS, key=lambda a: a.level)
        created_ids = {}
        for tmpl in sorted_accounts:
            if tmpl.code in existing_codes:
                result.skipped_accounts += 1
                continue
            parent_id = None
            if tmpl.parent_code:
                parent = GLAccount.query.filter_by(
                    tenant_id=tenant.id, code=tmpl.parent_code
                ).first()
                if parent:
                    parent_id = parent.id
            acc = GLAccount(
                tenant_id=tenant.id,
                code=tmpl.code,
                name=tmpl.name,
                name_ar=tmpl.name_ar,
                type=tmpl.type,
                level=tmpl.level,
                is_header=tmpl.is_header,
                parent_id=parent_id,
                industry_code=tmpl.industry_code,
                module_code=tmpl.module_code,
                currency=tenant.default_currency or 'AED',
                is_active=True,
            )
            db.session.add(acc)
            db.session.flush()
            created_ids[tmpl.code] = acc.id
            result.created_accounts += 1
    @staticmethod
    def _provision_industry_accounts(tenant: Tenant, result: ProvisionResult) -> None:
        industry = (tenant.business_type or 'general').strip().lower()
        if industry not in INDUSTRY_EXTENSIONS:
            return
        existing_codes = {
            row[0] for row in
            db.session.query(GLAccount.code).filter_by(tenant_id=tenant.id).all()
        }
        for tmpl in INDUSTRY_EXTENSIONS[industry]:
            if tmpl.code in existing_codes:
                result.skipped_accounts += 1
                continue
            parent_id = None
            if tmpl.parent_code:
                parent = GLAccount.query.filter_by(
                    tenant_id=tenant.id, code=tmpl.parent_code
                ).first()
                if parent:
                    parent_id = parent.id
            acc = GLAccount(
                tenant_id=tenant.id,
                code=tmpl.code,
                name=tmpl.name,
                name_ar=tmpl.name_ar,
                type=tmpl.type,
                level=tmpl.level,
                is_header=tmpl.is_header,
                parent_id=parent_id,
                industry_code=industry,
                module_code=tmpl.module_code,
                currency=tenant.default_currency or 'AED',
                is_active=True,
            )
            db.session.add(acc)
            db.session.flush()
            result.created_accounts += 1
    @staticmethod
    def _provision_module_mappings(tenant: Tenant, result: ProvisionResult) -> None:
        existing_mappings = {
            row[0] for row in
            db.session.query(GLAccountMapping.concept_code).filter_by(
                tenant_id=tenant.id, branch_id=None
            ).all()
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
                concept_meta = GL_CONCEPT_REGISTRY.get(mapping.concept_code, {})
                if concept_meta.get('resolution_mode', RESOLUTION_MODE_MAPPING) != RESOLUTION_MODE_MAPPING:
                    result.skipped_mappings += 1
                    continue
                account = GLAccount.query.filter_by(
                    tenant_id=tenant.id, code=mapping.account_code
                ).first()
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
        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            return []
        existing = {
            row[0] for row in
            db.session.query(GLAccount.code).filter_by(tenant_id=tenant_id).all()
        }
        missing = []
        for tmpl in BASE_ACCOUNTS:
            if tmpl.code not in existing:
                missing.append(tmpl)
        industry = (tenant.business_type or 'general').strip().lower()
        if industry in INDUSTRY_EXTENSIONS:
            for tmpl in INDUSTRY_EXTENSIONS[industry]:
                if tmpl.code not in existing:
                    missing.append(tmpl)
        return missing
    @staticmethod
    def get_missing_mappings(tenant_id: int) -> list:
        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            return []
        existing = {
            row[0] for row in
            db.session.query(GLAccountMapping.concept_code).filter_by(
                tenant_id=tenant_id, branch_id=None
            ).all()
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
        result = {
            'tenant_id': tenant_id,
            'accounts_ok': False,
            'mappings_ok': False,
            'missing_accounts': [],
            'missing_mappings': [],
            'errors': [],
        }
        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            result['errors'].append('Tenant not found')
            return result
        result['missing_accounts'] = [
            {'code': a.code, 'name': a.name, 'name_ar': a.name_ar}
            for a in GLProvisioningService.get_missing_accounts(tenant_id)
        ]
        result['missing_mappings'] = [
            {'concept': m.concept_code, 'account': m.account_code}
            for m in GLProvisioningService.get_missing_mappings(tenant_id)
        ]
        result['accounts_ok'] = len(result['missing_accounts']) == 0
        result['mappings_ok'] = len(result['missing_mappings']) == 0
        return result
