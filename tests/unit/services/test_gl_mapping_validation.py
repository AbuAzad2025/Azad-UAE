from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa

from extensions import db
from models import Branch, GLAccountMapping, Tenant
from models._constants import (
    GL_CONCEPT_AR,
    GL_CONCEPT_CASH,
    GL_CONCEPT_FIXED_ASSET_ASSET,
    GL_CONCEPT_INVENTORY_ASSET,
    REQUIRED_GL_CONCEPTS,
    RESOLUTION_MODE_LIQUIDITY,
    RESOLUTION_MODE_MAPPING,
    RESOLUTION_MODE_RECORD,
)
from models.gl import GLAccount
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


def _gl_account(db_session, tenant, code, name='Acct', account_type='asset', active=True, header=False):
    acct = GLAccount(
        tenant_id=tenant.id,
        code=code,
        name=name,
        type=account_type,
        is_active=active,
        is_header=header,
    )
    db_session.add(acct)
    db_session.flush()
    return acct


def _mapping(db_session, tenant, concept_code, gl_account, branch_id=None):
    m = GLAccountMapping(
        tenant_id=tenant.id,
        concept_code=concept_code,
        gl_account_id=gl_account.id,
        branch_id=branch_id,
        is_active=True,
    )
    db_session.add(m)
    db_session.flush()
    return m


def _minimal_tenant(db_session, prefix='Other'):
    unique = uuid.uuid4().hex[:8]
    tenant = Tenant(
        name=f'{prefix} {unique}',
        name_ar=f'{prefix} {unique}',
        slug=f'{prefix.lower()}-{unique}',
        email=f'{prefix.lower()}-{unique}@test.com',
        country='AE',
        is_active=True,
    )
    db_session.add(tenant)
    db_session.flush()
    return tenant


class TestHelpers:
    def test_tenant_name_prefers_name(self):
        tenant = type('T', (), {'id': 1, 'name': 'Primary', 'name_en': 'EN', 'name_ar': 'AR'})()
        assert _tenant_name(tenant) == 'Primary'

    def test_tenant_name_fallback(self):
        tenant = type('T', (), {'id': 5, 'name': None, 'name_en': None, 'name_ar': None})()
        assert _tenant_name(tenant) == 'Tenant 5'

    def test_concept_meta_unknown(self):
        assert _concept_meta('UNKNOWN')['required'] is False

    def test_severity_required_critical(self):
        required = next(iter(REQUIRED_GL_CONCEPTS))
        assert _severity_for(required) == 'critical'

    def test_severity_optional_warning(self):
        assert _severity_for('SOME_OPTIONAL') == 'warning'

    def test_recommended_fix_ready(self):
        assert _recommended_fix('ready', '') == 'No action required.'

    def test_recommended_fix_missing(self):
        assert 'Assign an existing' in _recommended_fix('missing', '')

    def test_recommended_fix_tenant_issue(self):
        assert 'same tenant' in _recommended_fix('invalid', 'belongs to another tenant')

    def test_recommended_fix_inactive(self):
        assert 'active GL account' in _recommended_fix('invalid', 'Account is inactive')

    def test_recommended_fix_header(self):
        assert 'postable detail' in _recommended_fix('invalid', 'header account')

    def test_recommended_fix_duplicate(self):
        assert 'duplicate' in _recommended_fix('invalid', 'duplicate mapping')

    def test_recommended_fix_default(self):
        assert _recommended_fix('invalid', 'other issue') == 'Review and correct the GL mapping manually.'

    def test_is_mapping_owned_default(self):
        assert _is_mapping_owned(GL_CONCEPT_AR) is True

    def test_is_mapping_owned_liquidity(self):
        assert _is_mapping_owned(GL_CONCEPT_CASH) is False

    def test_is_mapping_owned_record(self):
        assert _is_mapping_owned(GL_CONCEPT_FIXED_ASSET_ASSET) is False

    def test_row_builds_dataclass(self, sample_tenant):
        row = _row(sample_tenant, GL_CONCEPT_AR, 'ready', 'ok', severity='info')
        assert row.tenant_id == sample_tenant.id
        assert row.status == 'ready'

    def test_dataclass_to_dict(self, sample_tenant):
        row = GLMappingValidationRow(
            tenant_id=1,
            tenant_name='T',
            concept_code=GL_CONCEPT_AR,
            expected_legacy_code='1130',
            status='ready',
            issue='ok',
            severity='info',
            recommended_fix='none',
        )
        assert row.to_dict()['concept_code'] == GL_CONCEPT_AR

    def test_seed_preview_to_dict(self):
        row = GLMappingSeedPreviewRow(
            tenant_id=1,
            tenant_name='T',
            concept_code=GL_CONCEPT_AR,
            expected_legacy_code='1130',
            proposed_gl_account_id=1,
            proposed_gl_account_code='1130',
            proposed_gl_account_name='AR',
            status='proposed',
            issue='ok',
            severity='info',
            recommended_fix='approve',
        )
        assert row.to_dict()['status'] == 'proposed'

    def test_discovery_row_to_dict(self):
        row = GLMappingCandidateDiscoveryRow(
            tenant_id=1,
            tenant_name='T',
            concept_code='CASH',
            candidate_gl_account_id=1,
            candidate_gl_account_code='1110',
            candidate_gl_account_name='Cash',
            candidate_reason='match',
            confidence='high',
            status='candidate_found',
            recommended_fix='approve',
        )
        assert row.to_dict()['confidence'] == 'high'


class TestValidateTenant:
    def test_missing_tenant(self):
        rows = GLMappingValidationService.validate_tenant(999999)
        assert len(rows) == 1
        assert rows[0].status == 'invalid'

    def test_missing_required_mapping(self, db_session, sample_tenant):
        rows = GLMappingValidationService.validate_tenant(sample_tenant.id, include_ready=False)
        missing = [r for r in rows if r.status == 'missing' and r.concept_code in REQUIRED_GL_CONCEPTS]
        assert missing

    def test_valid_required_mapping_ready(self, db_session, sample_tenant):
        acct = _gl_account(db_session, sample_tenant, '1130', 'AR')
        _mapping(db_session, sample_tenant, GL_CONCEPT_AR, acct)
        rows = GLMappingValidationService.validate_tenant(sample_tenant.id, include_ready=True)
        ready = [r for r in rows if r.concept_code == GL_CONCEPT_AR and r.status == 'ready']
        assert ready

    def test_duplicate_required_mapping_invalid(self, db_session, sample_tenant):
        acct1 = _gl_account(db_session, sample_tenant, f'1130-{uuid.uuid4().hex[:4]}', 'AR1')
        acct2 = _gl_account(db_session, sample_tenant, f'1131-{uuid.uuid4().hex[:4]}', 'AR2')
        mapping_one = _mapping(db_session, sample_tenant, GL_CONCEPT_AR, acct1)
        mapping_two = MagicMock(
            id=mapping_one.id + 1,
            tenant_id=sample_tenant.id,
            concept_code=GL_CONCEPT_AR,
            gl_account_id=acct2.id,
            gl_account=acct2,
            branch_id=None,
            branch=None,
            is_active=True,
        )
        rows = GLMappingValidationService._validate_required_defaults(
            sample_tenant,
            [mapping_one, mapping_two],
            include_ready=False,
        )
        dup = [r for r in rows if r.concept_code == GL_CONCEPT_AR and 'Duplicate' in r.issue]
        assert dup

    def test_cross_tenant_account_invalid(self, sample_tenant):
        foreign = MagicMock(tenant_id=sample_tenant.id + 1, is_active=True, is_header=False)
        mapping = MagicMock(
            id=1,
            tenant_id=sample_tenant.id,
            concept_code=GL_CONCEPT_AR,
            gl_account=foreign,
            branch_id=None,
            branch=None,
            is_active=True,
        )
        issues = GLMappingValidationService._mapping_issues(sample_tenant, mapping)
        assert any('different tenant' in i.lower() for i in issues)

    def test_inactive_account_invalid(self, db_session, sample_tenant):
        acct = _gl_account(db_session, sample_tenant, '1130', 'AR', active=False)
        _mapping(db_session, sample_tenant, GL_CONCEPT_AR, acct)
        rows = GLMappingValidationService.validate_tenant(sample_tenant.id, include_ready=False)
        inactive = [r for r in rows if 'inactive' in r.issue.lower()]
        assert inactive

    def test_header_account_invalid(self, db_session, sample_tenant):
        acct = _gl_account(db_session, sample_tenant, '1130', 'AR Header', header=True)
        _mapping(db_session, sample_tenant, GL_CONCEPT_AR, acct)
        rows = GLMappingValidationService.validate_tenant(sample_tenant.id, include_ready=False)
        header = [r for r in rows if 'header' in r.issue.lower()]
        assert header

    def test_liquidity_readiness_missing(self, db_session, sample_tenant, sample_branch):
        rows = GLMappingValidationService.validate_tenant(sample_tenant.id, include_ready=False)
        liquidity = [r for r in rows if r.concept_code in ('CASH_READINESS', 'BANK_READINESS')]
        assert liquidity

    def test_liquidity_readiness_ok(self, db_session, sample_tenant, sample_branch):
        _gl_account(
            db_session,
            sample_tenant,
            f'111-{uuid.uuid4().hex[:4]}',
            'Cash',
            account_type='asset',
        )
        cash = GLAccount.query.filter_by(tenant_id=sample_tenant.id).order_by(GLAccount.id.desc()).first()
        cash.branch_id = sample_branch.id
        cash.liquidity_kind = 'cash'
        db_session.flush()
        rows = GLMappingValidationService.validate_tenant(sample_tenant.id, include_ready=False)
        cash_ready = [r for r in rows if r.concept_code == 'CASH_READINESS']
        assert not cash_ready

    def test_stale_non_mapping_owned_warning(self, db_session, sample_tenant):
        acct = _gl_account(db_session, sample_tenant, '1200', 'Fixed Asset')
        _mapping(db_session, sample_tenant, GL_CONCEPT_FIXED_ASSET_ASSET, acct)
        rows = GLMappingValidationService.validate_tenant(sample_tenant.id, include_ready=False)
        stale = [r for r in rows if r.concept_code == GL_CONCEPT_FIXED_ASSET_ASSET and r.status == 'warning']
        assert stale

    def test_branch_override_wrong_tenant(self, db_session, sample_tenant):
        other_branch = MagicMock(tenant_id=sample_tenant.id + 1, id=99)
        acct = _gl_account(db_session, sample_tenant, '1140', 'Inventory')
        mapping = MagicMock(
            id=1,
            tenant_id=sample_tenant.id,
            concept_code=GL_CONCEPT_INVENTORY_ASSET,
            gl_account=acct,
            branch_id=other_branch.id,
            branch=other_branch,
            is_active=True,
        )
        issues = GLMappingValidationService._mapping_issues(sample_tenant, mapping)
        assert any('Branch override belongs' in i for i in issues)


class TestDryRun:
    def test_dry_run_missing_table(self, mocker):
        inspector = MagicMock()
        inspector.has_table.return_value = False
        mocker.patch('sqlalchemy.inspect', return_value=inspector)
        result = GLMappingValidationService.dry_run(tenant_id=1)
        assert result['ready'] is False
        assert result['critical_count'] == 1

    def test_dry_run_all_tenants(self, mocker, sample_tenant):
        inspector = MagicMock()
        inspector.has_table.return_value = True
        mocker.patch('sqlalchemy.inspect', return_value=inspector)
        mocker.patch.object(
            GLMappingValidationService,
            'validate_all_tenants',
            return_value=[{'severity': 'critical', 'status': 'missing'}],
        )
        result = GLMappingValidationService.dry_run()
        assert 'rows' in result
        assert 'report_fields' in result

    def test_dry_run_single_tenant_counts(self, mocker, db_session, sample_tenant):
        inspector = MagicMock()
        inspector.has_table.return_value = True
        mocker.patch('sqlalchemy.inspect', return_value=inspector)
        result = GLMappingValidationService.dry_run(tenant_id=sample_tenant.id, include_ready=False)
        assert result['critical_count'] >= 1

    def test_module_wrappers(self, mocker, sample_tenant):
        inspector = MagicMock()
        inspector.has_table.return_value = True
        mocker.patch('sqlalchemy.inspect', return_value=inspector)
        mocker.patch.object(GLMappingValidationService, 'validate_all_tenants', return_value=[])
        mocker.patch.object(GLMappingValidationService, 'preview_seed', return_value={'rows': []})
        mocker.patch.object(GLMappingValidationService, 'discover_candidates', return_value={'rows': []})
        assert 'rows' in dry_run_gl_mapping_validation()
        assert 'rows' in preview_seed_gl_mapping(tenant_id=sample_tenant.id)
        assert 'rows' in discover_candidates_gl_mapping(tenant_id=sample_tenant.id)


class TestValidateAllTenants:
    def test_validate_all_tenants(self, mocker, sample_tenant):
        mocker.patch.object(
            GLMappingValidationService,
            'validate_tenant',
            return_value=[GLMappingValidationRow(
                tenant_id=sample_tenant.id,
                tenant_name='T',
                concept_code=GL_CONCEPT_AR,
                expected_legacy_code='1130',
                status='missing',
                issue='missing',
                severity='critical',
                recommended_fix='fix',
            )],
        )
        mocker.patch(
            'services.gl_mapping_validation.Tenant.query'
        ).order_by.return_value.all.return_value = [sample_tenant]
        rows = GLMappingValidationService.validate_all_tenants(include_ready=False)
        assert isinstance(rows, list)
        assert rows[0]['concept_code'] == GL_CONCEPT_AR


class TestPreviewSeed:
    def test_preview_seed_all_tenants(self, db_session, sample_tenant, mocker):
        mocker.patch('services.gl_mapping_validation.Tenant.query').order_by.return_value.all.return_value = [sample_tenant]
        result = GLMappingValidationService.preview_seed()
        assert result['preview_type'] == 'safe_seed_preview'
        assert 'rows' in result

    def test_preview_seed_single_tenant(self, db_session, sample_tenant):
        result = GLMappingValidationService.preview_seed(tenant_id=sample_tenant.id)
        assert result['proposed_count'] >= 0

    def test_preview_seed_unknown_tenant(self):
        result = GLMappingValidationService.preview_seed(tenant_id=999999)
        assert result['rows'] == []

    def test_preview_proposed_legacy_match(self, db_session, sample_tenant):
        _gl_account(db_session, sample_tenant, '1130', 'Accounts Receivable')
        rows = GLMappingValidationService._preview_seed_for_tenant(sample_tenant)
        proposed = [r for r in rows if r['concept_code'] == GL_CONCEPT_AR and r['status'] == 'proposed']
        assert proposed

    def test_preview_manual_required_no_legacy(self, db_session, sample_tenant):
        rows = GLMappingValidationService._preview_seed_for_tenant(sample_tenant)
        manual = [r for r in rows if r['status'] == 'manual_required' and r['expected_legacy_code'] is None]
        assert manual

    def test_preview_invalid_candidate(self, db_session, sample_tenant):
        _gl_account(db_session, sample_tenant, '1130', 'AR Header', header=True)
        rows = GLMappingValidationService._preview_seed_for_tenant(sample_tenant)
        invalid = [r for r in rows if r['concept_code'] == GL_CONCEPT_AR and r['status'] == 'invalid_candidate']
        assert invalid

    def test_account_issues_cross_tenant(self, sample_tenant):
        acct = MagicMock(tenant_id=sample_tenant.id + 1, is_active=True, is_header=False)
        issues = GLMappingValidationService._account_issues(sample_tenant, acct)
        assert any('different tenant' in i for i in issues)


class TestDiscoverCandidates:
    def test_discover_candidates(self, db_session, sample_tenant, mocker):
        mocker.patch.object(
            GLMappingValidationService,
            '_discover_for_tenant',
            return_value=[{
                'tenant_id': sample_tenant.id,
                'concept_code': 'CASH',
                'status': 'manual_creation_required',
            }],
        )
        result = GLMappingValidationService.discover_candidates(tenant_id=sample_tenant.id)
        assert result['discovery_type'] == 'candidate_discovery'
        assert result['total_concepts_checked'] > 0

    def test_find_candidates_exact_name(self, db_session, sample_tenant):
        _gl_account(db_session, sample_tenant, '1111', 'cash', account_type='asset')
        rule = {
            'name_exact': ['cash'],
            'name_partial': [],
            'expected_types': ['asset'],
        }
        found = GLMappingValidationService._find_candidates(sample_tenant, 'CASH', rule)
        assert found
        assert found[0][2] == 'high'

    def test_find_candidates_partial_name(self, db_session, sample_tenant):
        _gl_account(db_session, sample_tenant, '1112', 'Main Cashbox', account_type='asset')
        rule = {
            'name_exact': [],
            'name_partial': ['cashbox'],
            'expected_types': ['asset'],
        }
        found = GLMappingValidationService._find_candidates(sample_tenant, 'CASH', rule)
        assert found
        assert found[0][2] == 'medium'

    def test_find_candidates_parent_hint(self, db_session, sample_tenant):
        parent = _gl_account(db_session, sample_tenant, '1110', 'Cash Parent', header=True)
        child = _gl_account(db_session, sample_tenant, '1111', 'Petty Cash', account_type='asset')
        child.parent_id = parent.id
        db_session.flush()
        rule = {
            'name_exact': [],
            'name_partial': [],
            'expected_types': ['asset'],
            'parent_code_hint': '1110',
        }
        found = GLMappingValidationService._find_candidates(sample_tenant, 'CASH', rule)
        assert found

    def test_discover_manual_creation_when_no_candidates(self, db_session, sample_tenant, mocker):
        mocker.patch.object(GLMappingValidationService, '_preview_seed_for_tenant', return_value=[])
        mocker.patch.object(GLMappingValidationService, '_find_candidates', return_value=[])
        rows = GLMappingValidationService._discover_for_tenant(sample_tenant)
        manual = [r for r in rows if r['status'] == 'manual_creation_required']
        assert manual

    def test_discover_owner_selection_multiple(self, db_session, sample_tenant, mocker):
        acct1 = _gl_account(db_session, sample_tenant, 'C1', 'cash', account_type='asset')
        acct2 = _gl_account(db_session, sample_tenant, 'C2', 'cash', account_type='asset')
        mocker.patch.object(
            GLMappingValidationService,
            '_find_candidates',
            return_value=[
                (acct1, 'match1', 'high'),
                (acct2, 'match2', 'high'),
            ],
        )
        mocker.patch.object(GLMappingValidationService, '_preview_seed_for_tenant', return_value=[])
        rows = GLMappingValidationService._discover_for_tenant(sample_tenant)
        owner = [r for r in rows if r['status'] == 'owner_selection_required']
        assert owner

    def test_discover_skips_proposed_concepts(self, db_session, sample_tenant, mocker):
        mocker.patch.object(
            GLMappingValidationService,
            '_preview_seed_for_tenant',
            return_value=[{'concept_code': 'CASH', 'status': 'proposed'}],
        )
        rows = GLMappingValidationService._discover_for_tenant(sample_tenant)
        cash_rows = [r for r in rows if r['concept_code'] == 'CASH']
        assert not cash_rows


class TestMappingIssues:
    def test_unknown_concept_code(self, db_session, sample_tenant):
        acct = _gl_account(db_session, sample_tenant, '9999', 'Misc')
        mapping = MagicMock(
            concept_code='NOT_A_REAL_CODE',
            gl_account=acct,
            branch_id=None,
            branch=None,
            is_active=True,
        )
        issues = GLMappingValidationService._mapping_issues(sample_tenant, mapping)
        assert any('unknown' in i.lower() for i in issues)

    def test_missing_gl_account(self, sample_tenant):
        mapping = MagicMock(
            concept_code=GL_CONCEPT_AR,
            gl_account=None,
            branch_id=None,
            branch=None,
            is_active=True,
        )
        issues = GLMappingValidationService._mapping_issues(sample_tenant, mapping)
        assert any('does not exist' in i for i in issues)

    def test_inactive_mapping(self, db_session, sample_tenant):
        acct = _gl_account(db_session, sample_tenant, '1130', 'AR')
        mapping = MagicMock(
            concept_code=GL_CONCEPT_AR,
            gl_account=acct,
            branch_id=None,
            branch=None,
            is_active=False,
        )
        issues = GLMappingValidationService._mapping_issues(sample_tenant, mapping)
        assert any('mapping is inactive' in i for i in issues)
