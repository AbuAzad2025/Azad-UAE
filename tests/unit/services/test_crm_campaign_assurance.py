from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest


class TestLeadConversion:
    """CRMLeadService.convert_to_customer — idempotent, log-migration, duplicate guard."""

    def test_conversion_creates_customer(self, mocker, mock_db):
        mock_lead = MagicMock()
        mock_lead.id = 1
        mock_lead.tenant_id = 1
        mock_lead.branch_id = 1
        mock_lead.name = 'Ahmed'
        mock_lead.email = 'ahmed@test.com'
        mock_lead.phone = '0501111111'
        mock_lead.customer_id = None
        mock_lead.status = 'open'
        mock_lead.closed_at = None
        mocker.patch('services.crm_lead_service.db.session.get', return_value=mock_lead)

        mock_user = MagicMock()
        mock_user.id = 42
        mock_user.is_owner = False
        mock_user.tenant_id = 1
        mock_user.branch_id = 1
        mocker.patch('services.crm_lead_service.is_global_user', return_value=False)
        mocker.patch('services.crm_lead_service.branch_scope_id_for', return_value=1)
        mocker.patch('services.crm_lead_service.get_active_tenant_id', return_value=1)

        Customer = mocker.patch('services.crm_lead_service.Customer')
        Customer.query.filter.return_value.first.return_value = None
        mock_customer_instance = MagicMock()
        mock_customer_instance.id = 100
        Customer.return_value = mock_customer_instance

        CRMActivity = mocker.patch('services.crm_lead_service.CRMActivity')

        from services.crm_lead_service import CRMLeadService
        result = CRMLeadService.convert_to_customer(1, mock_user)

        assert result.id == 100
        assert mock_lead.customer_id == 100
        assert mock_lead.status == 'won'
        assert mock_lead.closed_at is not None
        CRMActivity.assert_called_once()

    def test_conversion_blocks_duplicate_email(self, mocker, mock_db):
        mock_lead = MagicMock()
        mock_lead.id = 1
        mock_lead.tenant_id = 1
        mock_lead.name = 'Ahmed'
        mock_lead.email = 'ahmed@test.com'
        mock_lead.phone = '0501111111'
        mock_lead.customer_id = None
        mocker.patch('services.crm_lead_service.db.session.get', return_value=mock_lead)

        mock_user = MagicMock()
        mock_user.id = 42
        mock_user.is_owner = False
        mock_user.tenant_id = 1
        mock_user.branch_id = 1
        mocker.patch('services.crm_lead_service.is_global_user', return_value=False)
        mocker.patch('services.crm_lead_service.branch_scope_id_for', return_value=1)
        mocker.patch('services.crm_lead_service.get_active_tenant_id', return_value=1)

        existing = MagicMock()
        existing.email = 'ahmed@test.com'
        existing.phone = '0502222222'
        Customer = mocker.patch('services.crm_lead_service.Customer')
        Customer.query.filter.return_value.first.return_value = existing

        from services.crm_lead_service import CRMLeadService
        with pytest.raises(ValueError, match='يوجد عميل مسجل بالفعل'):
            CRMLeadService.convert_to_customer(1, mock_user)

    def test_conversion_blocks_duplicate_phone(self, mocker, mock_db):
        mock_lead = MagicMock()
        mock_lead.id = 1
        mock_lead.tenant_id = 1
        mock_lead.email = 'unique@test.com'
        mock_lead.phone = '0501111111'
        mock_lead.customer_id = None
        mocker.patch('services.crm_lead_service.db.session.get', return_value=mock_lead)

        mock_user = MagicMock()
        mock_user.id = 42
        mocker.patch('services.crm_lead_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.crm_lead_service.is_global_user', return_value=False)
        mocker.patch('services.crm_lead_service.branch_scope_id_for', return_value=1)

        existing = MagicMock()
        existing.email = 'other@test.com'
        existing.phone = '0501111111'
        Customer = mocker.patch('services.crm_lead_service.Customer')
        Customer.query.filter.return_value.first.return_value = existing

        from services.crm_lead_service import CRMLeadService
        with pytest.raises(ValueError, match='يوجد عميل مسجل بالفعل'):
            CRMLeadService.convert_to_customer(1, mock_user)

    def test_conversion_returns_existing_customer(self, mocker, mock_db):
        mock_customer = MagicMock()
        mock_customer.id = 99
        mock_lead = MagicMock()
        mock_lead.id = 1
        mock_lead.tenant_id = 1
        mock_lead.customer_id = 99
        mock_lead.email = 'x@y.com'
        mock_lead.phone = '0500000000'
        mocker.patch('services.crm_lead_service.db.session.get', side_effect=lambda model, pk: {
            (CRMLead, 1): mock_lead,
            (Customer, 99): mock_customer,
        }.get((model, pk)))

        mock_user = MagicMock()
        mock_user.id = 42
        mocker.patch('services.crm_lead_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.crm_lead_service.is_global_user', return_value=False)
        mocker.patch('services.crm_lead_service.branch_scope_id_for', return_value=1)

        from services.crm_lead_service import CRMLeadService, CRMLead, Customer
        result = CRMLeadService.convert_to_customer(1, mock_user)
        assert result.id == 99

    def test_conversion_lead_not_found(self, mocker, mock_db):
        mocker.patch('services.crm_lead_service.db.session.get', return_value=None)
        mock_user = MagicMock()
        mock_user.id = 42
        from services.crm_lead_service import CRMLeadService
        with pytest.raises(ValueError, match='العميل المتوقع غير موجود'):
            CRMLeadService.convert_to_customer(999, mock_user)

    def test_conversion_no_email_no_phone_skips_dup_check(self, mocker, mock_db):
        mock_lead = MagicMock()
        mock_lead.id = 1
        mock_lead.tenant_id = 1
        mock_lead.branch_id = 1
        mock_lead.name = 'NoContact'
        mock_lead.email = None
        mock_lead.phone = None
        mock_lead.customer_id = None
        mock_lead.status = 'open'
        mock_lead.closed_at = None
        mocker.patch('services.crm_lead_service.db.session.get', return_value=mock_lead)

        mock_user = MagicMock()
        mock_user.id = 42
        mocker.patch('services.crm_lead_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.crm_lead_service.is_global_user', return_value=False)
        mocker.patch('services.crm_lead_service.branch_scope_id_for', return_value=1)

        Customer = mocker.patch('services.crm_lead_service.Customer')
        mock_customer = MagicMock()
        mock_customer.id = 101
        Customer.return_value = mock_customer
        Customer.query.filter.return_value.first.return_value = None

        from services.crm_lead_service import CRMLeadService
        result = CRMLeadService.convert_to_customer(1, mock_user)
        assert result.id == 101


class TestCampaignROI:
    """CampaignService ROI metrics — zero-cost guard, edge cases."""

    def test_roi_positive(self):
        from services.campaign_service import CampaignService
        roi = CampaignService.calculate_roi(Decimal('100'), Decimal('150'))
        assert roi == Decimal('50.00')

    def test_roi_zero_cost(self):
        from services.campaign_service import CampaignService
        roi = CampaignService.calculate_roi(Decimal('0'), Decimal('150'))
        assert roi == Decimal('0')

    def test_roi_zero_revenue(self):
        from services.campaign_service import CampaignService
        roi = CampaignService.calculate_roi(Decimal('100'), Decimal('0'))
        assert roi == Decimal('-100.00')

    def test_roi_negative(self):
        from services.campaign_service import CampaignService
        roi = CampaignService.calculate_roi(Decimal('200'), Decimal('50'))
        assert roi == Decimal('-75.00')

    def test_get_campaign_roi_metrics(self):
        mock_campaign = MagicMock()
        mock_campaign.id = 1
        mock_campaign.name = 'Ramadan Sale'
        mock_campaign.discount_value = Decimal('50')
        mock_campaign.usage_count = 10

        from services.campaign_service import CampaignService
        metrics = CampaignService.get_campaign_roi_metrics(mock_campaign, total_revenue=Decimal('1000'))
        assert metrics['campaign_id'] == 1
        assert metrics['total_cost'] == 500.0
        assert metrics['roi'] == 100.0
        assert metrics['total_revenue'] == 1000.0

    def test_get_campaign_roi_metrics_zero_cost(self):
        mock_campaign = MagicMock()
        mock_campaign.id = 2
        mock_campaign.name = 'Zero Budget'
        mock_campaign.discount_value = Decimal('0')
        mock_campaign.usage_count = 0

        from services.campaign_service import CampaignService
        metrics = CampaignService.get_campaign_roi_metrics(mock_campaign, total_revenue=Decimal('0'))
        assert metrics['total_cost'] == 0.0
        assert metrics['roi'] == 0.0

    def test_safe_commission_normal(self):
        from services.campaign_service import CampaignService
        commission = CampaignService.calculate_safe_commission(Decimal('1000'), Decimal('10'))
        assert commission == Decimal('100.00')

    def test_safe_commission_zero_revenue(self):
        from services.campaign_service import CampaignService
        commission = CampaignService.calculate_safe_commission(Decimal('0'), Decimal('10'))
        assert commission == Decimal('0.00')

    def test_safe_commission_rate_clamped(self):
        from services.campaign_service import CampaignService
        assert CampaignService.safe_commission_rate(Decimal('-5')) == Decimal('0')
        assert CampaignService.safe_commission_rate(Decimal('150')) == Decimal('100')
        assert CampaignService.safe_commission_rate(Decimal('15')) == Decimal('15')

    def test_safe_commission_none_inputs(self):
        from services.campaign_service import CampaignService
        assert CampaignService.calculate_safe_commission(None, None) == Decimal('0.00')
        assert CampaignService.calculate_safe_commission(Decimal('500'), None) == Decimal('0.00')


class TestBranchIsolation:
    """Branch-scoped lead isolation — non-global users blocked from cross-branch access."""

    def test_get_lead_wrong_branch_blocked(self, mocker, mock_db):
        mock_lead = MagicMock()
        mock_lead.id = 1
        mock_lead.tenant_id = 1
        mock_lead.branch_id = 2
        mocker.patch('services.crm_lead_service.db.session.get', return_value=mock_lead)
        mocker.patch('services.crm_lead_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.crm_lead_service.is_global_user', return_value=False)
        mocker.patch('services.crm_lead_service.branch_scope_id_for', return_value=1)

        from services.crm_lead_service import CRMLeadService
        with pytest.raises(ValueError, match='لا يمكنك التعامل مع عميل متوقع من فرع آخر'):
            CRMLeadService.get_lead(1, MagicMock())

    def test_get_lead_same_branch_allowed(self, mocker, mock_db):
        mock_lead = MagicMock()
        mock_lead.id = 1
        mock_lead.tenant_id = 1
        mock_lead.branch_id = 1
        mocker.patch('services.crm_lead_service.db.session.get', return_value=mock_lead)
        mocker.patch('services.crm_lead_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.crm_lead_service.is_global_user', return_value=False)
        mocker.patch('services.crm_lead_service.branch_scope_id_for', return_value=1)

        from services.crm_lead_service import CRMLeadService
        result = CRMLeadService.get_lead(1, MagicMock())
        assert result.id == 1

    def test_move_stage_wrong_branch_blocked(self, mocker, mock_db):
        mock_lead = MagicMock()
        mock_lead.id = 1
        mock_lead.tenant_id = 1
        mock_lead.branch_id = 2
        mocker.patch('services.crm_lead_service.db.session.get', return_value=mock_lead)
        mocker.patch('services.crm_lead_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.crm_lead_service.is_global_user', return_value=False)
        mocker.patch('services.crm_lead_service.branch_scope_id_for', return_value=1)

        from services.crm_lead_service import CRMLeadService
        with pytest.raises(ValueError, match='لا يمكنك التعامل مع عميل متوقع من فرع آخر'):
            CRMLeadService.move_stage(1, 5, MagicMock())

    def test_global_user_bypasses_branch_check(self, mocker, mock_db):
        mock_lead = MagicMock()
        mock_lead.id = 1
        mock_lead.tenant_id = 1
        mock_lead.branch_id = 2
        mocker.patch('services.crm_lead_service.db.session.get', return_value=mock_lead)
        mocker.patch('services.crm_lead_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.crm_lead_service.is_global_user', return_value=True)

        from services.crm_lead_service import CRMLeadService
        result = CRMLeadService.get_lead(1, MagicMock())
        assert result.id == 1

    def _make_mock_crm_lead(self, q):
        m = MagicMock(name='CRMLead')
        m.query = q
        return m

    def test_search_leads_filters_by_branch(self, mocker, mock_db):
        mock_q = MagicMock(name='query')
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value.all.return_value = []
        mock_model = self._make_mock_crm_lead(mock_q)
        mocker.patch('services.crm_lead_service.CRMLead', mock_model)
        mocker.patch('services.crm_lead_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.crm_lead_service.is_global_user', return_value=False)
        mocker.patch('services.crm_lead_service.branch_scope_id_for', return_value=1)

        from services.crm_lead_service import CRMLeadService
        CRMLeadService.search_leads({}, MagicMock())

        assert mock_q.filter.call_count >= 3

    def test_global_user_search_sees_all_branches(self, mocker, mock_db):
        mock_q = MagicMock(name='query')
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value.all.return_value = []
        mock_model = self._make_mock_crm_lead(mock_q)
        mocker.patch('services.crm_lead_service.CRMLead', mock_model)
        mocker.patch('services.crm_lead_service.get_active_tenant_id', return_value=1)
        mocker.patch('services.crm_lead_service.is_global_user', return_value=True)

        from services.crm_lead_service import CRMLeadService
        CRMLeadService.search_leads({}, MagicMock())

        assert mock_q.filter.call_count == 2


class TestKpiTracking:
    """KPI updates and goal achievement rating on conversion pipeline wins."""

    def _patch_crm_lead(self, mocker, count_side_effect):
        mock_model = MagicMock(name='CRMLead')
        mock_q = MagicMock(name='query')
        mock_q.filter.return_value = mock_q
        mock_q.count.side_effect = count_side_effect
        mock_model.query = mock_q
        mocker.patch('services.crm_lead_service.CRMLead', mock_model)
        mocker.patch('services.crm_lead_service.get_active_tenant_id', return_value=1)

    def test_compute_kpi_returns_zeros(self, mocker):
        self._patch_crm_lead(mocker, [0, 0])
        from services.crm_lead_service import CRMLeadService
        kpi = CRMLeadService.compute_conversion_kpi(MagicMock())
        assert kpi['total_converted'] == 0
        assert kpi['total_leads'] == 0
        assert kpi['conversion_rate'] == 0.0

    def test_compute_kpi_with_conversions(self, mocker):
        self._patch_crm_lead(mocker, [5, 10])
        from services.crm_lead_service import CRMLeadService
        kpi = CRMLeadService.compute_conversion_kpi(MagicMock())
        assert kpi['total_converted'] == 5
        assert kpi['total_leads'] == 10
        assert kpi['conversion_rate'] == 50.0

    def test_goal_achievement_rating_meets_target(self, mocker):
        self._patch_crm_lead(mocker, [5, 10])
        from services.crm_lead_service import CRMLeadService
        rating = CRMLeadService.compute_goal_achievement_rating(MagicMock(), 5)
        assert rating['target'] == 5
        assert rating['achieved'] == 5
        assert rating['rating'] == 100.0

    def test_goal_achievement_rating_above_target(self, mocker):
        self._patch_crm_lead(mocker, [8, 10])
        from services.crm_lead_service import CRMLeadService
        rating = CRMLeadService.compute_goal_achievement_rating(MagicMock(), 5)
        assert rating['achieved'] == 8
        assert rating['rating'] == 160.0

    def test_goal_achievement_zero_target(self, mocker):
        self._patch_crm_lead(mocker, [0, 0])
        from services.crm_lead_service import CRMLeadService
        rating = CRMLeadService.compute_goal_achievement_rating(MagicMock(), 0)
        assert rating['rating'] == 100.0
