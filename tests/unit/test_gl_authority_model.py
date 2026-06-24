"""GL authority-model resolution tests for Phase 2B-2.

Tests verify that the four resolution modes (mapping, liquidity, record,
non_posting) dispatch correctly and that stale legacy mappings are harmless.
"""

import uuid
import pytest
from datetime import datetime, timezone
from decimal import Decimal


# ---------------------------------------------------------------------------
# Module-level: reuse session app; enable dynamic GL mapping for this module
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module', autouse=True)
def _enable_dynamic_gl_mapping(app):
    prev = {
        'ENABLE_DYNAMIC_GL_MAPPING': app.config.get('ENABLE_DYNAMIC_GL_MAPPING'),
        'SERVER_NAME': app.config.get('SERVER_NAME'),
    }
    app.config.update({
        'SERVER_NAME': 'test.local',
        'ENABLE_DYNAMIC_GL_MAPPING': True,
    })
    yield
    app.config['ENABLE_DYNAMIC_GL_MAPPING'] = prev['ENABLE_DYNAMIC_GL_MAPPING']
    if prev['SERVER_NAME'] is not None:
        app.config['SERVER_NAME'] = prev['SERVER_NAME']


# ===================================================================
# 1. Provisioning scope
# ===================================================================

class TestProvisioningScope:
    """Fresh provisioning creates mappings only for mapping-owned concepts."""

    def test_provision_creates_no_liquidity_record_nonposting_mappings(self, app):
        from extensions import db
        from models import Tenant, Branch, GLAccountMapping
        from services.gl_provisioning_service import GLProvisioningService

        with app.app_context():
            tenant = Tenant(name=f"PrvScope1-{uuid.uuid4().hex[:6]}", name_ar='بروف سكوب', name_en='PrvScope1', slug=f"prv-scope-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()

            branch = Branch(tenant_id=tenant.id, name='Main', code='P1M', is_main=True)
            db.session.add(branch)
            db.session.flush()

            prov = GLProvisioningService.provision_tenant(tenant.id)
            db.session.flush()
            assert not prov.errors, f"Provisioning errors: {prov.errors}"

            mappings = GLAccountMapping.query.filter_by(tenant_id=tenant.id).all()
            concept_codes = {m.concept_code for m in mappings}

            not_expected = {'CASH', 'BANK', 'LANDED_COST',
                            'FIXED_ASSET_ASSET', 'DEPRECIATION_EXPENSE',
                            'ACCUMULATED_DEPRECIATION'}
            for code in not_expected:
                assert code not in concept_codes, f"{code} mapping must not exist"

            expected = {'AR', 'AP', 'INVENTORY_ASSET', 'COGS',
                        'SALES_REVENUE', 'VAT_INPUT', 'VAT_OUTPUT'}
            for code in expected:
                assert code in concept_codes, f"{code} mapping must exist"

    def test_no_mapping_targets_header_inactive_foreign(self, app):
        from extensions import db
        from models import Tenant, GLAccountMapping, GLAccount
        from services.gl_provisioning_service import GLProvisioningService

        with app.app_context():
            tenant = Tenant(name=f"PrvScope2-{uuid.uuid4().hex[:6]}", name_ar='بروف سكوب 2', name_en='PrvScope2', slug=f"prv-scope-2-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()

            prov = GLProvisioningService.provision_tenant(tenant.id)
            assert not prov.errors

            mappings = GLAccountMapping.query.filter_by(tenant_id=tenant.id).all()
            for mapping in mappings:
                account = db.session.get(GLAccount, mapping.gl_account_id)
                assert account is not None, f"Mapping {mapping.concept_code} -> missing account"
                assert account.is_active, f"Mapping {mapping.concept_code} -> inactive {account.code}"
                assert not account.is_header, f"Mapping {mapping.concept_code} -> header {account.code}"
                assert account.tenant_id == tenant.id, f"Mapping {mapping.concept_code} -> foreign {account.code}"


# ===================================================================
# 2. Liquidity mode
# ===================================================================

class TestLiquidityMode:
    """Branch CASH/BANK line uses the branch's actual liquidity account
    even when a stale tenant-level mapping exists."""

    def _setup_tenant_branch(self, app, name):
        from extensions import db
        from models import Tenant, Branch
        tenant = Tenant(name=f"{name}-{uuid.uuid4().hex[:6]}", name_ar=name, name_en=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}", default_currency='AED')
        db.session.add(tenant)
        db.session.flush()
        branch = Branch(tenant_id=tenant.id, name='Main', code=f'{name[:3]}M', is_main=True)
        db.session.add(branch)
        db.session.flush()
        return tenant, branch

    def _create_stale_mapping(self, app, tenant, concept_code):
        from extensions import db
        from models import GLAccountMapping, GLAccount
        header = GLAccount.query.filter_by(tenant_id=tenant.id, is_header=True).first()
        if not header:
            return None
        stale = GLAccountMapping(
            tenant_id=tenant.id,
            concept_code=concept_code,
            gl_account_id=header.id,
            branch_id=None,
            is_active=True,
        )
        db.session.add(stale)
        db.session.flush()
        return stale

    def test_branch_cash_bypasses_stale_mapping(self, app):
        from extensions import db
        from models import GLAccount, GLJournalEntry, GLJournalLine
        from services.gl_provisioning_service import GLProvisioningService
        from services.gl_tree_builder import GLTreeBuilder
        from services.gl_service import GLService

        with app.app_context():
            tenant, branch = self._setup_tenant_branch(app, 'LiqCash')
            GLProvisioningService.provision_tenant(tenant.id)
            GLTreeBuilder.build(tenant.id)
            db.session.commit()

            cash_acc = GLAccount.query.filter_by(
                tenant_id=tenant.id, branch_id=branch.id, liquidity_kind='cash'
            ).first()
            assert cash_acc is not None

            self._create_stale_mapping(app, tenant, 'CASH')
            db.session.commit()

            entry = GLService.create_journal_entry(
                date=datetime(2026, 6, 1, tzinfo=timezone.utc),
                description='Test cash',
                lines=[
                    {
                        'account_code': cash_acc.code,
                        'concept_code': 'CASH',
                        'debit': 100,
                        'credit': 0,
                        'description': 'Cash test',
                    },
                    {
                        'concept_code': 'AR',
                        'debit': 0,
                        'credit': 100,
                        'description': 'Balancing AR',
                    },
                ],
                branch_id=branch.id,
                tenant_id=tenant.id,
            )
            db.session.commit()

            cash_line = GLJournalLine.query.filter_by(entry_id=entry.id).filter(
                GLJournalLine.debit > 0
            ).first()
            posted = db.session.get(GLAccount, cash_line.account_id)
            assert posted.id == cash_acc.id, (
                f"Expected {cash_acc.id} ({cash_acc.code}), got {posted.id} ({posted.code})"
            )

    def test_branch_bank_bypasses_stale_mapping(self, app):
        from extensions import db
        from models import GLAccount, GLJournalEntry, GLJournalLine
        from services.gl_provisioning_service import GLProvisioningService
        from services.gl_tree_builder import GLTreeBuilder
        from services.gl_service import GLService

        with app.app_context():
            tenant, branch = self._setup_tenant_branch(app, 'LiqBank')
            GLProvisioningService.provision_tenant(tenant.id)
            GLTreeBuilder.build(tenant.id)
            db.session.commit()

            bank_acc = GLAccount.query.filter_by(
                tenant_id=tenant.id, branch_id=branch.id, liquidity_kind='bank'
            ).first()
            assert bank_acc is not None

            self._create_stale_mapping(app, tenant, 'BANK')
            db.session.commit()

            entry = GLService.create_journal_entry(
                date=datetime(2026, 6, 1, tzinfo=timezone.utc),
                description='Test bank',
                lines=[
                    {
                        'account_code': bank_acc.code,
                        'concept_code': 'BANK',
                        'debit': 200,
                        'credit': 0,
                        'description': 'Bank test',
                    },
                    {
                        'concept_code': 'AR',
                        'debit': 0,
                        'credit': 200,
                        'description': 'Balancing AR',
                    },
                ],
                branch_id=branch.id,
                tenant_id=tenant.id,
            )
            db.session.commit()

            bank_line = GLJournalLine.query.filter_by(entry_id=entry.id).filter(
                GLJournalLine.debit > 0
            ).first()
            posted = db.session.get(GLAccount, bank_line.account_id)
            assert posted.id == bank_acc.id, (
                f"Expected {bank_acc.id} ({bank_acc.code}), got {posted.id} ({posted.code})"
            )

    def test_liquidity_requires_account_code(self, app):
        from extensions import db
        from services.gl_service import GLService
        from services.gl_account_resolver import GLMappingError

        with app.app_context():
            tenant, branch = self._setup_tenant_branch(app, 'LiqReq')
            from services.gl_provisioning_service import GLProvisioningService
            GLProvisioningService.provision_tenant(tenant.id)
            db.session.commit()

            with pytest.raises(GLMappingError, match='requires an explicit GL account code'):
                GLService.create_journal_entry(
                    date=datetime(2026, 6, 1, tzinfo=timezone.utc),
                    description='No account code',
                    lines=[{
                        'concept_code': 'CASH',
                        'debit': 100,
                        'credit': 0,
                        'description': 'Bad line',
                    }],
                    branch_id=branch.id,
                    tenant_id=tenant.id,
                )


# ===================================================================
# 3. Record mode
# ===================================================================

class TestRecordMode:
    """FixedAsset depreciation/disposal posts to exact stored accounts."""

    def _setup_asset(self, app, tenant, branch, asset_number, purchase_price=10000):
        from extensions import db
        from models import GLAccount
        from models.fixed_asset import FixedAsset
        from decimal import Decimal

        asset_acc = GLAccount.query.filter_by(tenant_id=tenant.id, code='1111').first()
        dep_exp_acc = GLAccount.query.filter_by(tenant_id=tenant.id, code='6300').first()
        dep_acc = GLAccount.query.filter_by(tenant_id=tenant.id, code='1190').first()

        asset = FixedAsset(
            tenant_id=tenant.id,
            asset_number=asset_number,
            name_ar='أصل اختبار',
            asset_account_id=asset_acc.id,
            depreciation_account_id=dep_acc.id,
            expense_account_id=dep_exp_acc.id,
            purchase_date='2026-01-01',
            purchase_price=Decimal(str(purchase_price)),
            useful_life_years=5,
            category='equipment',
            branch_id=branch.id,
        )
        db.session.add(asset)
        db.session.flush()
        return asset, asset_acc, dep_acc, dep_exp_acc

    def test_depreciation_posts_to_exact_accounts(self, app):
        from extensions import db
        from models import GLAccount, GLJournalLine
        from services.gl_provisioning_service import GLProvisioningService
        from services.gl_tree_builder import GLTreeBuilder

        with app.app_context():
            from models import Tenant, Branch
            tenant = Tenant(name=f"RecDepr-{uuid.uuid4().hex[:6]}", name_ar='ريك دبر', name_en='RecDepr', slug=f"rec-depr-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()
            branch = Branch(tenant_id=tenant.id, name='Main', code='RDM', is_main=True)
            db.session.add(branch)
            db.session.flush()

            GLProvisioningService.provision_tenant(tenant.id)
            GLTreeBuilder.build(tenant.id)
            db.session.commit()

            asset, asset_acc, dep_acc, dep_exp_acc = self._setup_asset(
                app, tenant, branch, 'FA-DEPR', 10000
            )
            db.session.commit()

            sched = asset.post_depreciation(period_date='2026-02-01')
            db.session.commit()
            assert sched is not None

            lines = GLJournalLine.query.filter_by(
                entry_id=sched.journal_entry_id
            ).order_by(GLJournalLine.id).all()
            assert len(lines) == 2

            acc0 = db.session.get(GLAccount, lines[0].account_id)
            acc1 = db.session.get(GLAccount, lines[1].account_id)

            assert acc0.id == dep_exp_acc.id, (
                f"Expected expense {dep_exp_acc.id}, got {acc0.id}"
            )
            assert acc1.id == dep_acc.id, (
                f"Expected depreciation {dep_acc.id}, got {acc1.id}"
            )

    def test_disposal_posts_to_exact_asset_account(self, app):
        from extensions import db
        from models import GLAccount, GLAccountMapping, GLJournalLine, GLJournalEntry
        from services.gl_provisioning_service import GLProvisioningService
        from services.gl_tree_builder import GLTreeBuilder
        from utils.gl_reference_types import GLRef

        with app.app_context():
            from models import Tenant, Branch
            tenant = Tenant(name=f"RecDis-{uuid.uuid4().hex[:6]}", name_ar='ريك دس', name_en='RecDis', slug=f"rec-dis-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()
            branch = Branch(tenant_id=tenant.id, name='Main', code='RDM2', is_main=True)
            db.session.add(branch)
            db.session.flush()

            GLProvisioningService.provision_tenant(tenant.id)
            GLTreeBuilder.build(tenant.id)
            db.session.commit()

            asset, asset_acc, dep_acc, dep_exp_acc = self._setup_asset(
                app, tenant, branch, 'FA-DIS', 5000
            )
            db.session.commit()

            gain_acc = GLAccount.query.filter_by(tenant_id=tenant.id, code='4600').first()
            loss_acc = GLAccount.query.filter_by(tenant_id=tenant.id, code='6700').first()
            for ccode, cacc in (('FIXED_ASSET_GAIN', gain_acc), ('FIXED_ASSET_LOSS', loss_acc)):
                if not GLAccountMapping.query.filter_by(tenant_id=tenant.id, concept_code=ccode).first():
                    mapping = GLAccountMapping(
                        tenant_id=tenant.id, concept_code=ccode,
                        gl_account_id=cacc.id, branch_id=None, is_active=True,
                    )
                    db.session.add(mapping)
            db.session.commit()

            asset.post_depreciation(period_date='2026-02-01')
            db.session.commit()

            asset.dispose(disposal_date='2026-03-01', disposal_price=3000)
            db.session.commit()

            entries = GLJournalEntry.query.filter_by(
                tenant_id=tenant.id,
                reference_type=GLRef.ASSET_DISPOSAL,
                reference_id=asset.id,
            ).all()
            assert len(entries) >= 1
            entry = entries[-1]

            lines = GLJournalLine.query.filter_by(entry_id=entry.id).all()
            asset_line = None
            for line in lines:
                acct = db.session.get(GLAccount, line.account_id)
                if acct and acct.id == asset_acc.id:
                    asset_line = line
                    break
            assert asset_line is not None, "No line posting to asset account"
            assert asset_line.credit > 0, "Asset line should be credit"

    def test_record_requires_explicit_account_allowed(self, app):
        from extensions import db
        from services.gl_service import GLService
        from services.gl_account_resolver import GLMappingError

        with app.app_context():
            from models import Tenant, Branch
            from services.gl_provisioning_service import GLProvisioningService
            tenant = Tenant(name=f"RecReq-{uuid.uuid4().hex[:6]}", name_ar='ريك ريك', name_en='RecReq', slug=f"rec-req-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()
            branch = Branch(tenant_id=tenant.id, name='Main', code='RRM', is_main=True)
            db.session.add(branch)
            db.session.flush()
            GLProvisioningService.provision_tenant(tenant.id)
            db.session.commit()

            with pytest.raises(GLMappingError, match='requires explicit_account_allowed=True'):
                GLService.create_journal_entry(
                    date=datetime(2026, 6, 1, tzinfo=timezone.utc),
                    description='No explicit flag',
                    lines=[{
                        'account_code': '1111',
                        'concept_code': 'FIXED_ASSET_ASSET',
                        'debit': 100,
                        'credit': 0,
                        'description': 'Bad line',
                    }],
                    branch_id=branch.id,
                    tenant_id=tenant.id,
                )


# ===================================================================
# 4. Mapping mode — GAIN/LOSS use mapping
# ===================================================================

class TestMappingMode:
    """FIXED_ASSET_GAIN and FIXED_ASSET_LOSS resolve through mapping."""

    def test_gain_loss_mappings_exist_and_are_valid(self, app):
        from extensions import db
        from models import Tenant, GLAccountMapping, GLAccount
        from services.gl_provisioning_service import GLProvisioningService

        with app.app_context():
            tenant = Tenant(name=f"MapGL-{uuid.uuid4().hex[:6]}", name_ar='ماب جل', name_en='MapGL', slug=f"map-gl-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()

            GLProvisioningService.provision_tenant(tenant.id)
            db.session.commit()

            gain_acc = GLAccount.query.filter_by(tenant_id=tenant.id, code='4600').first()
            loss_acc = GLAccount.query.filter_by(tenant_id=tenant.id, code='6700').first()
            assert gain_acc is not None and gain_acc.is_active and not gain_acc.is_header
            assert loss_acc is not None and loss_acc.is_active and not loss_acc.is_header

            for code, acc in (('FIXED_ASSET_GAIN', gain_acc), ('FIXED_ASSET_LOSS', loss_acc)):
                if not GLAccountMapping.query.filter_by(tenant_id=tenant.id, concept_code=code).first():
                    mapping = GLAccountMapping(
                        tenant_id=tenant.id, concept_code=code,
                        gl_account_id=acc.id, branch_id=None, is_active=True,
                    )
                    db.session.add(mapping)
            db.session.commit()

            for code in ('FIXED_ASSET_GAIN', 'FIXED_ASSET_LOSS'):
                mapping = GLAccountMapping.query.filter_by(
                    tenant_id=tenant.id, concept_code=code
                ).first()
                assert mapping is not None, f"{code} mapping missing"
                account = db.session.get(GLAccount, mapping.gl_account_id)
                assert account is not None, f"{code} -> missing"
                assert account.is_active, f"{code} -> inactive"
                assert not account.is_header, f"{code} -> header"

    def test_gain_loss_resolves_through_resolver(self, app):
        from extensions import db
        from models import Tenant, GLAccountMapping, GLAccount
        from services.gl_provisioning_service import GLProvisioningService
        from services.gl_account_resolver import resolve_gl_account

        with app.app_context():
            tenant = Tenant(name=f"MapGL2-{uuid.uuid4().hex[:6]}", name_ar='ماب جل 2', name_en='MapGL2', slug=f"map-gl-2-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()

            GLProvisioningService.provision_tenant(tenant.id)
            db.session.commit()

            gain_acc = GLAccount.query.filter_by(tenant_id=tenant.id, code='4600').first()
            loss_acc = GLAccount.query.filter_by(tenant_id=tenant.id, code='6700').first()

            gain_map = GLAccountMapping(
                tenant_id=tenant.id, concept_code='FIXED_ASSET_GAIN',
                gl_account_id=gain_acc.id, branch_id=None, is_active=True,
            )
            db.session.add(gain_map)
            loss_map = GLAccountMapping(
                tenant_id=tenant.id, concept_code='FIXED_ASSET_LOSS',
                gl_account_id=loss_acc.id, branch_id=None, is_active=True,
            )
            db.session.add(loss_map)
            db.session.commit()

            resolved_gain = resolve_gl_account(tenant.id, 'FIXED_ASSET_GAIN')
            assert resolved_gain is not None
            assert resolved_gain.id == gain_map.gl_account_id

            resolved_loss = resolve_gl_account(tenant.id, 'FIXED_ASSET_LOSS')
            assert resolved_loss is not None
            assert resolved_loss.id == loss_map.gl_account_id


# ===================================================================
# 5. Stale mapping warnings (read-only)
# ===================================================================

class TestStaleMappings:
    """Stale mappings for liquidity/record/non-posting are read-only warnings."""

    def test_stale_mappings_are_warnings_not_errors(self, app):
        from extensions import db
        from models import Tenant, GLAccount, GLAccountMapping
        from services.gl_provisioning_service import GLProvisioningService
        from services.gl_mapping_validation import GLMappingValidationService

        with app.app_context():
            tenant = Tenant(name=f"Stale1-{uuid.uuid4().hex[:6]}", name_ar='ستال 1', name_en='Stale1', slug=f"stale-1-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()

            GLProvisioningService.provision_tenant(tenant.id)
            db.session.commit()

            # NOTE: Do not create guessed mapping in tests per corrective commit
            # PURCHASES mapping insertion removed

            stale_concepts = ('CASH', 'BANK', 'LANDED_COST',
                              'FIXED_ASSET_ASSET', 'DEPRECIATION_EXPENSE',
                              'ACCUMULATED_DEPRECIATION')
            for code in stale_concepts:
                if not GLAccountMapping.query.filter_by(
                    tenant_id=tenant.id, concept_code=code
                ).first():
                    header = GLAccount.query.filter_by(
                        tenant_id=tenant.id, is_header=True
                    ).first()
                    if header:
                        stale = GLAccountMapping(
                            tenant_id=tenant.id,
                            concept_code=code,
                            gl_account_id=header.id,
                            branch_id=None,
                            is_active=True,
                        )
                        db.session.add(stale)
            db.session.commit()

            result = GLMappingValidationService.dry_run(
                tenant_id=tenant.id, include_ready=True
            )
            # NOTE: Do not claim result["ready"] is True per corrective commit
            # Stale mappings should not block readiness for mapping-owned concepts
            # but may still show as not ready due to missing required mappings

            for row in result['rows']:
                if row['concept_code'] in stale_concepts:
                    assert row['severity'] == 'warning', (
                        f"{row['concept_code']} should be warning, got {row['severity']}: {row['issue']}"
                    )
            # Additional assertion: stale mappings should be warnings regardless of
            # unrelated required mapping gaps (they are ignored during posting)
            stale_warnings = [r for r in result['rows'] if r['concept_code'] in stale_concepts]
            assert len(stale_warnings) == len(stale_concepts), \
                f"Expected {len(stale_concepts)} stale concept warnings, got {len(stale_warnings)}"
            for warning in stale_warnings:
                assert warning['severity'] == 'warning', \
                    f"Stale concept {warning['concept_code']} should be warning, got {warning['severity']}"

    def test_provisioner_rejects_header_target_mapping(self, app, monkeypatch):
        """Test that provisioning service rejects header account targets for mapping-owned concepts."""
        from extensions import db
        from models import Tenant
        from services.gl_provisioning_service import GLProvisioningService
        from models.gl_account_registry import GL_MODULE_DEFINITIONS, GLModuleDefinition, GLConceptMappingTemplate

        with app.app_context():
            tenant = Tenant(name=f"HdrTgt-{uuid.uuid4().hex[:6]}", name_ar='هدر هدف', name_en='HdrTgt', slug=f"hdr-tgt-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()

            # Create a header account (code 1000)
            from models import GLAccount
            header_acc = GLAccount(
                tenant_id=tenant.id,
                code='1000',
                name='Header Account',
                name_ar='حساب رئيسي',
                type='asset',
                level=1,
                is_header=True,
                is_active=True,
            )
            db.session.add(header_acc)
            db.session.flush()

            # Inject a mapping-owned concept targeting the header account code 1000
            injected_module = GLModuleDefinition(
                module_code='test_header_target',
                required=True,
                accounts=[],
                mappings=[GLConceptMappingTemplate('TEST_HEADER_TARGET', '1000', 'test_header_target')],
            )
            monkeypatch.setitem(GL_MODULE_DEFINITIONS, 'test_header_target', injected_module)

            prov = GLProvisioningService.provision_tenant(tenant.id)

            # No mapping should be created for the injected concept
            from models.gl import GLAccountMapping
            bad_mapping = GLAccountMapping.query.filter_by(
                tenant_id=tenant.id, concept_code='TEST_HEADER_TARGET'
            ).first()
            assert bad_mapping is None, "Mapping to header account should not be created"

            # Provisioning should report an error mentioning header
            assert any('is header' in e.lower() or 'header' in e.lower() for e in prov.errors), \
                f"Expected header error in prov.errors: {prov.errors}"


# ===================================================================
# 6. Tenant/Branch Isolation Validation
# ===================================================================

class TestTenantBranchIsolation:
    """Test tenant/branch isolation validation in GLService.create_journal_entry."""

    def test_entry_branch_from_another_tenant_is_rejected(self, app):
        """Entry branch from another tenant should be rejected."""
        from extensions import db
        from models import Tenant, Branch
        from services.gl_service import GLService, GLMappingError

        with app.app_context():
            # Create two tenants
            tenant1 = Tenant(name=f"Tenant1-{uuid.uuid4().hex[:6]}", name_ar=' tenant1', name_en='Tenant1', slug=f"tenant1-{uuid.uuid4().hex[:6]}", default_currency='AED')
            tenant2 = Tenant(name=f"Tenant2-{uuid.uuid4().hex[:6]}", name_ar=' tenant2', name_en='Tenant2', slug=f"tenant2-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add_all([tenant1, tenant2])
            db.session.flush()

            # Create a branch for tenant2
            branch2 = Branch(tenant_id=tenant2.id, name='Branch2', code='BR2', is_main=True)
            db.session.add(branch2)
            db.session.flush()

            # Provision both tenants
            from services.gl_provisioning_service import GLProvisioningService
            GLProvisioningService.provision_tenant(tenant1.id)
            GLProvisioningService.provision_tenant(tenant2.id)
            db.session.commit()

            # Use balanced mapping-owned lines (AR + SALES_REVENUE) to prove boundary failure occurs before posting
            with pytest.raises(GLMappingError, match=f"Branch {branch2.id} belongs to tenant {tenant2.id}, not tenant {tenant1.id}"):
                GLService.create_journal_entry(
                    date=datetime(2026, 6, 1, tzinfo=timezone.utc),
                    description='Test entry with wrong branch',
                    lines=[
                        {'concept_code': 'AR', 'debit': 100, 'credit': 0, 'description': 'AR line'},
                        {'concept_code': 'SALES_REVENUE', 'debit': 0, 'credit': 100, 'description': 'Revenue line'},
                    ],
                    branch_id=branch2.id,  # This branch belongs to tenant2
                    tenant_id=tenant1.id,  # But we're trying to use it with tenant1
                )

    def test_line_branch_from_another_tenant_is_rejected(self, app):
        """Line branch from another tenant should be rejected."""
        from extensions import db
        from models import Tenant, Branch
        from services.gl_service import GLService, GLMappingError

        with app.app_context():
            # Create two tenants
            tenant1 = Tenant(name=f"Tenant1-{uuid.uuid4().hex[:6]}", name_ar=' tenant1', name_en='Tenant1', slug=f"tenant1-{uuid.uuid4().hex[:6]}", default_currency='AED')
            tenant2 = Tenant(name=f"Tenant2-{uuid.uuid4().hex[:6]}", name_ar=' tenant2', name_en='Tenant2', slug=f"tenant2-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add_all([tenant1, tenant2])
            db.session.flush()

            # Create a branch for tenant2
            branch2 = Branch(tenant_id=tenant2.id, name='Branch2', code='BR2', is_main=True)
            db.session.add(branch2)
            db.session.flush()

            # Provision both tenants
            from services.gl_provisioning_service import GLProvisioningService
            GLProvisioningService.provision_tenant(tenant1.id)
            GLProvisioningService.provision_tenant(tenant2.id)
            db.session.commit()

            # Try to create journal entry with tenant1 and its own branch, but line with branch from tenant2
            with pytest.raises(GLMappingError, match=f"Line branch {branch2.id} belongs to tenant {tenant2.id}, not tenant {tenant1.id}"):
                GLService.create_journal_entry(
                    date=datetime(2026, 6, 1, tzinfo=timezone.utc),
                    description='Test entry with wrong line branch',
                    lines=[
                        {'concept_code': 'AR', 'debit': 100, 'credit': 0, 'description': 'AR line', 'branch_id': branch2.id},
                        {'concept_code': 'SALES_REVENUE', 'debit': 0, 'credit': 100, 'description': 'Revenue line', 'branch_id': branch2.id},
                    ],
                    branch_id=None,  # Entry has no specific branch
                    tenant_id=tenant1.id,  # But line uses tenant2's branch
                )

    def test_valid_same_tenant_different_line_branch_is_allowed(self, app):
        """Valid same-tenant different line branch should be allowed."""
        from extensions import db
        from models import Tenant, Branch
        from services.gl_service import GLService
        from services.gl_provisioning_service import GLProvisioningService
        from services.gl_tree_builder import GLTreeBuilder

        with app.app_context():
            # Create tenant with two branches
            tenant = Tenant(name=f"Tenant-{uuid.uuid4().hex[:6]}", name_ar=' tenant', name_en='Tenant', slug=f"tenant-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()

            # Create two branches for the same tenant
            branch1 = Branch(tenant_id=tenant.id, name='Branch1', code='BR1', is_main=True)
            branch2 = Branch(tenant_id=tenant.id, name='Branch2', code='BR2', is_main=False)
            db.session.add_all([branch1, branch2])
            db.session.flush()

            # Provision tenant and build tree
            GLProvisioningService.provision_tenant(tenant.id)
            GLTreeBuilder.build(tenant.id)
            db.session.commit()

            # This should work - same tenant, different branches for entry and line
            # Both journal lines explicitly use branch2; entry branch is branch1
            entry = GLService.create_journal_entry(
                date=datetime(2026, 6, 1, tzinfo=timezone.utc),
                description='Test entry with same tenant different branches',
                lines=[
                    {'concept_code': 'AR', 'debit': 100, 'credit': 0, 'description': 'AR line', 'branch_id': branch2.id},
                    {'concept_code': 'SALES_REVENUE', 'debit': 0, 'credit': 100, 'description': 'Revenue line', 'branch_id': branch2.id},
                ],
                branch_id=branch1.id,  # Entry uses branch1 (same tenant)
                tenant_id=tenant.id,
            )

            # Verify the entry was created successfully
            assert entry is not None
            assert entry.tenant_id == tenant.id
            assert entry.branch_id == branch1.id

            # Verify exactly two journal lines were created, both with branch_id == branch2.id
            from models import GLJournalLine
            lines = GLJournalLine.query.filter_by(entry_id=entry.id).all()
            assert len(lines) == 2
            for line in lines:
                assert line.branch_id == branch2.id


# ===================================================================
# 7. Additional authority model edge cases
# ===================================================================

class TestAuthorityModelEdgeCases:
    """Focused tests for GL authority model edge cases."""

    def test_ar_concept_code_case_insensitive(self, app):
        """' ar ' (with spaces, lowercase) resolves to same account as 'AR'."""
        from extensions import db
        from models import Tenant, Branch
        from services.gl_provisioning_service import GLProvisioningService
        from services.gl_tree_builder import GLTreeBuilder
        from services.gl_service import GLService
        from services.gl_account_resolver import resolve_gl_account

        with app.app_context():
            tenant = Tenant(name=f"ArCase-{uuid.uuid4().hex[:6]}", name_ar='ar case', name_en='ArCase', slug=f"arcase-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()
            branch = Branch(tenant_id=tenant.id, name='Main', code='ACM', is_main=True)
            db.session.add(branch)
            db.session.flush()

            GLProvisioningService.provision_tenant(tenant.id)
            GLTreeBuilder.build(tenant.id)
            db.session.commit()

            # Resolve AR with canonical case
            ar_canonical = resolve_gl_account(tenant_id=tenant.id, concept_code='AR', branch_id=branch.id)
            # Resolve ' ar ' with spaces and lowercase
            ar_variant = resolve_gl_account(tenant_id=tenant.id, concept_code=' ar ', branch_id=branch.id)

            assert ar_canonical is not None
            assert ar_variant is not None
            assert ar_canonical.id == ar_variant.id

    def test_unknown_concept_raises_glmappingerror(self, app):
        """Unknown non-empty concept raises GLMappingError containing 'Unknown GL concept'."""
        from extensions import db
        from models import Tenant, Branch
        from services.gl_provisioning_service import GLProvisioningService
        from services.gl_tree_builder import GLTreeBuilder
        from services.gl_account_resolver import resolve_gl_account, GLMappingError

        with app.app_context():
            tenant = Tenant(name=f"UnkConcept-{uuid.uuid4().hex[:6]}", name_ar='unk', name_en='UnkConcept', slug=f"unkconcept-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()
            branch = Branch(tenant_id=tenant.id, name='Main', code='UCM', is_main=True)
            db.session.add(branch)
            db.session.flush()

            GLProvisioningService.provision_tenant(tenant.id)
            GLTreeBuilder.build(tenant.id)
            db.session.commit()

            with pytest.raises(GLMappingError, match='Unknown GL concept'):
                resolve_gl_account(tenant_id=tenant.id, concept_code='DOES_NOT_EXIST', branch_id=branch.id)

    def test_branch_a_cash_rejected_when_resolved_with_branch_b(self, app):
        """Branch A CASH account is rejected when entry branch is B but account is from A."""
        from extensions import db
        from models import Tenant, Branch, GLAccount
        from services.gl_provisioning_service import GLProvisioningService
        from services.gl_tree_builder import GLTreeBuilder
        from services.gl_service import GLService
        from services.gl_account_resolver import GLMappingError

        with app.app_context():
            tenant = Tenant(name=f"LiqBranch-{uuid.uuid4().hex[:6]}", name_ar='liq', name_en='LiqBranch', slug=f"liqbranch-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()
            branch_a = Branch(tenant_id=tenant.id, name='BranchA', code='BRA', is_main=True)
            branch_b = Branch(tenant_id=tenant.id, name='BranchB', code='BRB', is_main=False)
            db.session.add_all([branch_a, branch_b])
            db.session.flush()

            GLProvisioningService.provision_tenant(tenant.id)
            GLTreeBuilder.build(tenant.id)
            db.session.commit()

            # Get branch A's CASH liquidity account
            cash_acc_a = GLAccount.query.filter_by(
                tenant_id=tenant.id, branch_id=branch_a.id, liquidity_kind='cash'
            ).first()
            assert cash_acc_a is not None

            # Create a balanced entry with branch_a using branch A's CASH account - should work
            entry_a = GLService.create_journal_entry(
                date=datetime(2026, 6, 1, tzinfo=timezone.utc),
                description='Test cash branch A',
                lines=[
                    {'account_code': cash_acc_a.code, 'concept_code': 'CASH', 'debit': 100, 'credit': 0, 'description': 'Cash line', 'branch_id': branch_a.id},
                    {'concept_code': 'AR', 'debit': 0, 'credit': 100, 'description': 'Balancing AR', 'branch_id': branch_a.id},
                ],
                branch_id=branch_a.id,
                tenant_id=tenant.id,
            )
            assert entry_a is not None

            # Try to create entry with entry branch=branch_b but using branch A's CASH account
            # This should be rejected because entry branch B doesn't match account's branch A
            with pytest.raises(GLMappingError, match="does not match required branch_id"):
                GLService.create_journal_entry(
                    date=datetime(2026, 6, 1, tzinfo=timezone.utc),
                    description='Test cash branch B rejection',
                    lines=[
                        {'account_code': cash_acc_a.code, 'concept_code': 'CASH', 'debit': 100, 'credit': 0, 'description': 'Cash line', 'branch_id': branch_b.id},
                        {'concept_code': 'AR', 'debit': 0, 'credit': 100, 'description': 'Balancing AR', 'branch_id': branch_b.id},
                    ],
                    branch_id=branch_b.id,
                    tenant_id=tenant.id,
                )

    def test_branch_a_bank_rejected_when_resolved_with_branch_b(self, app):
        """Branch A BANK account is rejected when entry branch is B but account is from A."""
        from extensions import db
        from models import Tenant, Branch, GLAccount
        from services.gl_provisioning_service import GLProvisioningService
        from services.gl_tree_builder import GLTreeBuilder
        from services.gl_service import GLService
        from services.gl_account_resolver import GLMappingError

        with app.app_context():
            tenant = Tenant(name=f"LiqBranchB-{uuid.uuid4().hex[:6]}", name_ar='liq', name_en='LiqBranchB', slug=f"liqbranchb-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()
            branch_a = Branch(tenant_id=tenant.id, name='BranchA', code='BRA', is_main=True)
            branch_b = Branch(tenant_id=tenant.id, name='BranchB', code='BRB', is_main=False)
            db.session.add_all([branch_a, branch_b])
            db.session.flush()

            GLProvisioningService.provision_tenant(tenant.id)
            GLTreeBuilder.build(tenant.id)
            db.session.commit()

            # Get branch A's BANK liquidity account
            bank_acc_a = GLAccount.query.filter_by(
                tenant_id=tenant.id, branch_id=branch_a.id, liquidity_kind='bank'
            ).first()
            assert bank_acc_a is not None

            # Create a balanced entry with branch_a using branch A's BANK account - should work
            entry_a = GLService.create_journal_entry(
                date=datetime(2026, 6, 1, tzinfo=timezone.utc),
                description='Test bank branch A',
                lines=[
                    {'account_code': bank_acc_a.code, 'concept_code': 'BANK', 'debit': 100, 'credit': 0, 'description': 'Bank line', 'branch_id': branch_a.id},
                    {'concept_code': 'AR', 'debit': 0, 'credit': 100, 'description': 'Balancing AR', 'branch_id': branch_a.id},
                ],
                branch_id=branch_a.id,
                tenant_id=tenant.id,
            )
            assert entry_a is not None

            # Try to create entry with entry branch=branch_b but using branch A's BANK account
            # This should be rejected because entry branch B doesn't match account's branch A
            with pytest.raises(GLMappingError, match="does not match required branch_id"):
                GLService.create_journal_entry(
                    date=datetime(2026, 6, 1, tzinfo=timezone.utc),
                    description='Test bank branch B rejection',
                    lines=[
                        {'account_code': bank_acc_a.code, 'concept_code': 'BANK', 'debit': 100, 'credit': 0, 'description': 'Bank line', 'branch_id': branch_b.id},
                        {'concept_code': 'AR', 'debit': 0, 'credit': 100, 'description': 'Balancing AR', 'branch_id': branch_b.id},
                    ],
                    branch_id=branch_b.id,
                    tenant_id=tenant.id,
                )

    def test_landed_cost_raises_with_dynamic_mapping_disabled(self, app, monkeypatch):
        """With ENABLE_DYNAMIC_GL_MAPPING=False, LANDED_COST still raises GLMappingError via GLService."""
        from extensions import db
        from models import Tenant, Branch
        from services.gl_provisioning_service import GLProvisioningService
        from services.gl_tree_builder import GLTreeBuilder
        from services.gl_service import GLService
        from services.gl_account_resolver import GLMappingError

        with app.app_context():
            # Disable dynamic GL mapping
            monkeypatch.setitem(app.config, 'ENABLE_DYNAMIC_GL_MAPPING', False)

            tenant = Tenant(name=f"LcDisabled-{uuid.uuid4().hex[:6]}", name_ar='lc', name_en='LcDisabled', slug=f"lcdisabled-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()
            branch = Branch(tenant_id=tenant.id, name='Main', code='LDM', is_main=True)
            db.session.add(branch)
            db.session.flush()

            GLProvisioningService.provision_tenant(tenant.id)
            GLTreeBuilder.build(tenant.id)
            db.session.commit()

            # LANDED_COST is non-posting; should raise even with dynamic mapping disabled
            # Use GLService._resolve_journal_line_account which has the non-posting check
            with pytest.raises(GLMappingError, match="Non-posting concept cannot be resolved"):
                GLService._resolve_journal_line_account(
                    {'concept_code': 'LANDED_COST'}, tenant_id=tenant.id, branch_id=branch.id
                )

    def test_cash_bank_readiness_before_build(self, app):
        """Before GLTreeBuilder.build(), dry_run reports critical CASH_READINESS and BANK_READINESS."""
        from extensions import db
        from models import Tenant, Branch
        from services.gl_provisioning_service import GLProvisioningService
        from services.gl_mapping_validation import GLMappingValidationService

        with app.app_context():
            tenant = Tenant(name=f"ReadyBefore-{uuid.uuid4().hex[:6]}", name_ar='ready', name_en='ReadyBefore', slug=f"readybefore-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()
            branch = Branch(tenant_id=tenant.id, name='Main', code='RBM', is_main=True)
            db.session.add(branch)
            db.session.flush()

            # Provision only (no GLTreeBuilder.build yet)
            GLProvisioningService.provision_tenant(tenant.id)
            db.session.commit()

            result = GLMappingValidationService.dry_run(tenant_id=tenant.id, include_ready=True)

            cash_rows = [r for r in result['rows'] if r['concept_code'] == 'CASH_READINESS']
            bank_rows = [r for r in result['rows'] if r['concept_code'] == 'BANK_READINESS']

            assert len(cash_rows) == 1, f"Expected 1 CASH_READINESS row, got {len(cash_rows)}"
            assert cash_rows[0]['severity'] == 'critical'
            assert len(bank_rows) == 1, f"Expected 1 BANK_READINESS row, got {len(bank_rows)}"
            assert bank_rows[0]['severity'] == 'critical'

    def test_cash_bank_readiness_after_build(self, app):
        """After GLTreeBuilder.build(), CASH_READINESS and BANK_READINESS rows are absent."""
        from extensions import db
        from models import Tenant, Branch
        from services.gl_provisioning_service import GLProvisioningService
        from services.gl_tree_builder import GLTreeBuilder
        from services.gl_mapping_validation import GLMappingValidationService

        with app.app_context():
            tenant = Tenant(name=f"ReadyAfter-{uuid.uuid4().hex[:6]}", name_ar='ready', name_en='ReadyAfter', slug=f"readyafter-{uuid.uuid4().hex[:6]}", default_currency='AED')
            db.session.add(tenant)
            db.session.flush()
            branch = Branch(tenant_id=tenant.id, name='Main', code='RAM', is_main=True)
            db.session.add(branch)
            db.session.flush()

            GLProvisioningService.provision_tenant(tenant.id)
            GLTreeBuilder.build(tenant.id)
            db.session.commit()

            result = GLMappingValidationService.dry_run(tenant_id=tenant.id, include_ready=True)

            cash_rows = [r for r in result['rows'] if r['concept_code'] == 'CASH_READINESS']
            bank_rows = [r for r in result['rows'] if r['concept_code'] == 'BANK_READINESS']

            # After build, liquidity accounts exist so readiness rows should be absent
            assert len(cash_rows) == 0, f"Expected 0 CASH_READINESS rows after build, got {len(cash_rows)}"
            assert len(bank_rows) == 0, f"Expected 0 BANK_READINESS rows after build, got {len(bank_rows)}"