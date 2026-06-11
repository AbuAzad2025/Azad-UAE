"""
Services Unit Tests
Tests service layer functions, business logic, and data transformation.
"""
import pytest
from decimal import Decimal


class TestExchangeRateService:
    """Test exchange rate service."""

    def test_get_online_rates_for_display(self, app):
        from services.exchange_rate_service import ExchangeRateService
        with app.app_context():
            result = ExchangeRateService.get_online_rates_for_display("USD")
            assert result["ok"] is True
            assert "rates" in result

    def test_display_fallback_has_aed(self, app):
        from services.exchange_rate_service import ExchangeRateService
        with app.app_context():
            result = ExchangeRateService.get_online_rates_for_display("USD", symbols=("AED",))
            assert result["ok"] is True
            assert "AED" in result["rates"]


class TestGLAccountResolver:
    """Test GL account resolver."""

    def test_is_dynamic_gl_mapping_enabled(self, app):
        from services.gl_account_resolver import is_dynamic_gl_mapping_enabled
        with app.app_context():
            result = is_dynamic_gl_mapping_enabled()
            assert isinstance(result, bool)


class TestGLHelpers:
    """Test GL helper functions."""

    def test_gl_helpers_import(self):
        from services import gl_helpers
        assert gl_helpers is not None


class TestFeatureFlagService:
    """Test feature flag service."""

    def test_feature_flags(self, app):
        from services.feature_flag_service import FeatureFlagService
        with app.app_context():
            assert hasattr(FeatureFlagService, "is_enabled")


class TestHealthService:
    """Test health service."""

    def test_health_check(self, app):
        from services.health_service import HealthCheckService
        with app.app_context():
            result = HealthCheckService.check_database()
            assert isinstance(result, dict)


class TaxServiceTest:
    """Test tax service."""

    def test_tax_service_exists(self):
        from services.tax_service import TaxService
        assert TaxService is not None


class TestNotificationService:
    """Test notification service."""

    def test_notification_service_import(self):
        from services.notification_service import NotificationService
        assert NotificationService is not None


class TestWebhookService:
    """Test webhook service."""

    def test_webhook_service_import(self):
        from services.webhook_service import WebhookService
        assert WebhookService is not None


class TestArchiveService:
    """Test archive service."""

    def test_archive_service_import(self):
        from services.archive_service import ArchiveService
        assert ArchiveService is not None


class TestAutoApprovalService:
    """Test auto-approval service."""

    def test_auto_approval_service_import(self):
        from services.auto_approval_service import AutoApprovalService
        assert AutoApprovalService is not None


class TestBankReconciliationService:
    """Test bank reconciliation service."""

    def test_bank_reconciliation_service_import(self):
        from services.bank_reconciliation_service import BankReconciliationService
        assert BankReconciliationService is not None


class TestCashFlowService:
    """Test cash flow service."""

    def test_cash_flow_service_import(self):
        from services.cash_flow_service import CashFlowService
        assert CashFlowService is not None


class TestPartnerService:
    """Test partner service."""

    def test_partner_service_import(self):
        from services.partner_service import PartnerService
        assert PartnerService is not None


class TestReturnService:
    """Test return service."""

    def test_return_service_import(self):
        from services.return_service import ReturnService
        assert ReturnService is not None


class TestPaymentService:
    """Test payment service."""

    def test_payment_service_import(self):
        from services.payment_service import PaymentService
        assert PaymentService is not None


class TestPurchaseService:
    """Test purchase service."""

    def test_purchase_service_import(self):
        from services.purchase_service import PurchaseService
        assert PurchaseService is not None


class TestAgingAnalysisService:
    """Test aging analysis service."""

    def test_aging_analysis_service_import(self):
        from services.aging_analysis_service import AgingAnalysisService
        assert AgingAnalysisService is not None


class TestCommissionGLService:
    """Test commission GL service."""

    def test_commission_gl_service_import(self):
        from services.commission_gl_service import post_sale_commissions
        assert callable(post_sale_commissions)


class TestDonationGLService:
    """Test donation GL service."""

    def test_donation_gl_service_import(self):
        from services.donation_gl_service import DonationGLService
        assert DonationGLService is not None


class TestEInvoiceService:
    """Test e-invoice service."""

    def test_einvoice_service_import(self):
        from services.einvoice_service import EInvoiceService
        assert EInvoiceService is not None


class TestGLPosting:
    """Test GL posting service."""

    def test_post_or_fail_exists(self):
        from services.gl_posting import post_or_fail
        assert callable(post_or_fail)

    def test_gl_posting_error_exists(self):
        from services.gl_posting import GlPostingError
        assert issubclass(GlPostingError, Exception)


class TestGLTreeBuilder:
    """Test GL tree builder."""

    def test_gl_tree_builder_import(self):
        from services.gl_tree_builder import GLTreeBuilder
        assert GLTreeBuilder is not None


class TestGLMappingValidation:
    """Test GL mapping validation."""

    def test_gl_mapping_validation_import(self):
        from services.gl_mapping_validation import GLMappingValidationService
        assert GLMappingValidationService is not None


class TestGLAccountResolver:
    """Test GL account resolver."""

    def test_resolve_gl_account_exists(self):
        from services.gl_account_resolver import resolve_gl_account
        assert callable(resolve_gl_account)

    def test_gl_mapping_error_exists(self):
        from services.gl_account_resolver import GLMappingError
        assert issubclass(GLMappingError, Exception)


class TestAnalyticsService:
    """Test analytics service."""

    def test_analytics_service_import(self):
        from services.analytics_service import AnalyticsService
        assert AnalyticsService is not None


class TestAdvancedAnalytics:
    """Test advanced analytics."""

    def test_advanced_analytics_import(self):
        from services.advanced_analytics import AdvancedFinancialAnalytics
        assert AdvancedFinancialAnalytics is not None


class TestPredictiveMaintenance:
    """Test predictive maintenance service."""

    def test_predictive_maintenance_import(self):
        from services.predictive_maintenance import PredictiveMaintenanceService
        assert PredictiveMaintenanceService is not None


class TestStoreService:
    """Test store service."""

    def test_store_service_import(self):
        from services.store_service import StoreService
        assert StoreService is not None


class TestStoreAnalyticsService:
    """Test store analytics service."""

    def test_store_analytics_service_import(self):
        from services.store_analytics_service import StoreAnalyticsService
        assert StoreAnalyticsService is not None


class TestStoreCheckoutService:
    """Test store checkout service."""

    def test_store_checkout_service_import(self):
        from services.store_checkout_service import StoreCheckoutService
        assert StoreCheckoutService is not None


class TestStoreCouponService:
    """Test store coupon service."""

    def test_store_coupon_service_import(self):
        from services.store_coupon_service import StoreCouponService
        assert StoreCouponService is not None

    def test_create_coupon_rejects_both_percent_and_amount(self, app, db_session):
        from services.store_coupon_service import StoreCouponService
        with app.app_context():
            with pytest.raises(ValueError, match='حدد نسبة أو مبلغ خصم، لا كلاهما'):
                StoreCouponService.create_coupon(1, {'code': 'BOTH01', 'discount_percent': 10, 'discount_amount': 50})

    def test_create_coupon_rejects_zero_percent(self, app, db_session):
        from services.store_coupon_service import StoreCouponService
        with app.app_context():
            with pytest.raises(ValueError, match='نسبة الخصم يجب أن تكون بين 0.01 و 100'):
                StoreCouponService.create_coupon(1, {'code': 'ZERO01', 'discount_percent': 0})

    def test_create_coupon_rejects_negative_amount(self, app, db_session):
        from services.store_coupon_service import StoreCouponService
        with app.app_context():
            with pytest.raises(ValueError, match='مبلغ الخصم يجب أن يكون أكبر من صفر'):
                StoreCouponService.create_coupon(1, {'code': 'NEG01', 'discount_amount': -10})

    def test_create_coupon_rejects_over_100_percent(self, app, db_session):
        from services.store_coupon_service import StoreCouponService
        with app.app_context():
            with pytest.raises(ValueError, match='نسبة الخصم يجب أن تكون بين 0.01 و 100'):
                StoreCouponService.create_coupon(1, {'code': 'OVER01', 'discount_percent': 101})


class TestStoreOrderService:
    """Test store order service."""

    def test_store_order_service_import(self):
        from services.store_order_service import StoreOrderService
        assert StoreOrderService is not None


class TestStorePaymentMethodService:
    """Test store payment method service."""

    def test_store_payment_method_service_import(self):
        from services.store_payment_method_service import StorePaymentMethodService
        assert StorePaymentMethodService is not None


class TestShopCustomerAuthService:
    """Test shop customer auth service."""

    def test_shop_customer_auth_service_import(self):
        from services.shop_customer_auth_service import ShopCustomerAuthService
        assert ShopCustomerAuthService is not None


class TestMonitoringService:
    """Test monitoring service."""

    def test_logging_core_import(self):
        from services.logging_core import LoggingCore
        assert LoggingCore is not None


class TestBackupService:
    """Test backup service."""

    def test_backup_service_import(self):
        from services.backup_service import BackupService
        assert BackupService is not None


class TestBackupExec:
    """Test backup exec service."""

    def test_backup_exec_import(self):
        from services.backup_exec import run_pg_tool
        assert callable(run_pg_tool)


class TestCurrencyService:
    """Test currency service."""

    def test_currency_service_import(self):
        from services.currency_service import CurrencyService
        assert CurrencyService is not None


class TestExportService:
    """Test export service."""

    def test_export_service_import(self):
        from services.export_service import ExportService
        assert ExportService is not None


class TestGamificationService:
    """Test gamification service."""

    def test_gamification_service_import(self):
        from services.gamification_service import GamificationService
        assert GamificationService is not None


class TestWhatsAppService:
    """Test WhatsApp service."""

    def test_whatsapp_service_import(self):
        from services.whatsapp_service import WhatsAppService
        assert WhatsAppService is not None


class TestPayrollService:
    """Test payroll service."""

    def test_payroll_service_import(self):
        from services.payroll_service import PayrollService
        assert PayrollService is not None


class TestCurrencyService:
    """Test currency service."""

    def test_currency_service_fallback_rate(self, app):
        from services.currency_service import CurrencyService
        with app.app_context():
            rate = CurrencyService.FALLBACK_RATES.get("AED")
            assert rate == Decimal("1.00")

    def test_currency_service_get_exchange_rate_fallback(self, app):
        from services.currency_service import CurrencyService
        with app.app_context():
            rate = CurrencyService.get_exchange_rate("AED", "AED")
            assert rate == Decimal("1.00")

    def test_currency_service_common_currencies(self, app):
        from services.currency_service import CurrencyService
        with app.app_context():
            assert "AED" in CurrencyService.COMMON_CURRENCIES
            assert "USD" in CurrencyService.COMMON_CURRENCIES


class TestGLService:
    """Test GL service."""

    def test_gl_service_import(self, app):
        from services.gl_service import GLService
        with app.app_context():
            assert GLService is not None

    def test_gl_accounts_dict(self, app):
        from services.gl_service import GL_ACCOUNTS
        with app.app_context():
            assert isinstance(GL_ACCOUNTS, dict)
            assert "cash" in GL_ACCOUNTS


class TestGLHelpers:
    """Test GL helpers."""

    def test_next_entry_number(self, app):
        from services.gl_helpers import next_entry_number
        with app.app_context():
            num = next_entry_number(1)
            assert num.startswith("JE-")


class TestInventoryReconciliationService:
    """Test inventory reconciliation service."""

    def test_inventory_reconciliation_import(self):
        from services.inventory_reconciliation_service import InventoryReconciliationService
        assert InventoryReconciliationService is not None


class TestChequeAccountingIntegration:
    """Test cheque accounting integration."""

    def test_cheque_accounting_import(self):
        from services.cheque_accounting_integration import ChequeAccountingIntegration
        assert ChequeAccountingIntegration is not None


class TestExportService:
    """Test export service."""

    def test_export_service_import(self):
        from services.export_service import ExportService
        assert ExportService is not None


class TestEInvoiceService:
    """Test e-invoice service."""

    def test_einvoice_service_import(self):
        from services.einvoice_service import EInvoiceService
        assert EInvoiceService is not None


class TestNotificationService:
    """Test notification service."""

    def test_notification_service_import(self):
        from services.notification_service import NotificationService
        assert NotificationService is not None


class TestWebhookService:
    """Test webhook service."""

    def test_webhook_service_import(self):
        from services.webhook_service import WebhookService
        assert WebhookService is not None


# ---------------------------------------------------------------------------
# services/feature_flag_service.py
# ---------------------------------------------------------------------------
class TestFeatureFlagResolution:
    def test_known_flag_from_config(self, app):
        from services.feature_flag_service import FeatureFlagService
        with app.app_context():
            assert FeatureFlagService.is_enabled("ENABLE_MWAC") is True

    def test_unknown_flag_false(self, app):
        from services.feature_flag_service import FeatureFlagService
        with app.app_context():
            assert FeatureFlagService.is_enabled("UNKNOWN_FLAG") is False

    def test_get_all_flags(self, app):
        from services.feature_flag_service import FeatureFlagService
        with app.app_context():
            flags = FeatureFlagService.get_all_flags()
            assert isinstance(flags, dict)
            assert "ENABLE_MWAC" in flags

    def test_require_enabled_raises(self, app):
        from services.feature_flag_service import FeatureFlagService
        with app.app_context():
            with pytest.raises(RuntimeError):
                FeatureFlagService.require_enabled("UNKNOWN_FLAG")


# ---------------------------------------------------------------------------
# services/currency_service.py
# ---------------------------------------------------------------------------
class TestCurrencyServiceLogic:
    def test_invalid_manual_rate_caught(self, app):
        from services.currency_service import CurrencyService
        with app.app_context():
            result = CurrencyService.get_exchange_rate_details("AED", "USD", user_rate="abc")
            assert isinstance(result, dict)
            assert "rate" in result
            assert result["source"] != "user_input"

    def test_same_currency_parity(self, app):
        from services.currency_service import CurrencyService
        with app.app_context():
            result = CurrencyService.get_exchange_rate_details("AED", "AED")
            assert result["rate"] == Decimal("1.000000")
            assert result["source"] == "parity"

    def test_currency_label(self):
        from services.currency_service import CurrencyService
        label = CurrencyService.get_currency_label("USD")
        assert "USD" in label
        assert "Dollar" in label


# ---------------------------------------------------------------------------
# services/gl_posting.py
# ---------------------------------------------------------------------------
class TestGLPostingBehaviour:
    def test_assert_balanced_lines_pass(self):
        from services.gl_posting import assert_balanced_lines
        lines = [
            {"debit": Decimal("100"), "credit": Decimal("0")},
            {"debit": Decimal("0"), "credit": Decimal("100")},
        ]
        assert_balanced_lines(lines)

    def test_assert_balanced_lines_fail(self):
        from services.gl_posting import assert_balanced_lines, GlPostingError
        lines = [
            {"debit": Decimal("100"), "credit": Decimal("0")},
            {"debit": Decimal("0"), "credit": Decimal("50")},
        ]
        with pytest.raises(GlPostingError):
            assert_balanced_lines(lines)

    def test_post_or_fail_empty_raises(self, app):
        from services.gl_posting import post_or_fail, GlPostingError
        with app.app_context():
            with pytest.raises(GlPostingError):
                post_or_fail([], description="empty")


# ---------------------------------------------------------------------------
# services/gl_account_resolver.py
# ---------------------------------------------------------------------------
class TestGLAccountResolverLogic:
    def test_dynamic_mapping_disabled(self):
        from services.gl_account_resolver import is_dynamic_gl_mapping_enabled
        assert is_dynamic_gl_mapping_enabled({"ENABLE_DYNAMIC_GL_MAPPING": False}) is False
        assert is_dynamic_gl_mapping_enabled({"ENABLE_DYNAMIC_GL_MAPPING": True}) is True

    def test_gl_mapping_error_message(self):
        from services.gl_account_resolver import GLMappingError
        err = GLMappingError(tenant_id=1, concept_code="X", branch_id=None, issue="missing")
        assert "missing" in str(err)
        assert "X" in str(err)


# ---------------------------------------------------------------------------
# services/gl_service.py
# ---------------------------------------------------------------------------
class TestGLServiceConcepts:
    def test_posting_line(self):
        from services.gl_service import GLService
        line = GLService.posting_line("cash", debit=100, credit=0, description="test")
        assert line["account"] == "1110"
        assert line["debit"] == 100
        assert line["concept_code"] == "CASH"

    def test_posting_line_override(self):
        from services.gl_service import GLService
        line = GLService.posting_line("cash", account="9999", concept_code="CUSTOM")
        assert line["account"] == "9999"
        assert line["concept_code"] == "CUSTOM"

    def test_payment_debit_concepts(self):
        from services.gl_service import GLService
        assert GLService.get_payment_debit_concept("cash") == "CASH"
        assert GLService.get_payment_debit_concept("bank_transfer") == "BANK"
        assert GLService.get_payment_debit_concept("cheque") == "CHEQUES_UNDER_COLLECTION"
        assert GLService.get_payment_debit_concept("") == "CASH"

    def test_payment_credit_concepts(self):
        from services.gl_service import GLService
        assert GLService.get_payment_credit_concept("cash") == "CASH"
        assert GLService.get_payment_credit_concept("card") == "BANK"
        assert GLService.get_payment_credit_concept("cheque") == "DEFERRED_CHEQUES_PAYABLE"
        assert GLService.get_payment_credit_concept("unknown") is None

    def test_customer_credit_concepts(self):
        from services.gl_service import GLService
        partner = type("C", (), {"customer_type": "partner"})()
        merchant = type("C", (), {"customer_type": "merchant"})()
        regular = type("C", (), {"customer_type": "individual"})()
        assert GLService.get_customer_credit_concept(partner) == "PARTNER_CURRENT_ACCOUNT"
        assert GLService.get_customer_credit_concept(merchant) == "MERCHANT_CURRENT_ACCOUNT"
        assert GLService.get_customer_credit_concept(regular) == "AR"
        assert GLService.get_customer_credit_concept(None) == "AR"


# ---------------------------------------------------------------------------
# services/gl_helpers.py
# ---------------------------------------------------------------------------
class TestGLHelpersLogic:
    def test_next_entry_number_format(self, app):
        from services.gl_helpers import next_entry_number
        with app.app_context():
            num = next_entry_number(1)
            assert num.startswith("JE-")

    def test_resolve_tenant_id_by_user(self, app, sample_user):
        from services.gl_helpers import resolve_tenant_id
        with app.app_context():
            tid = resolve_tenant_id(user_id=sample_user.id)
            assert tid == sample_user.tenant_id

    def test_assert_period_open_no_crash(self, app):
        from services.gl_helpers import assert_period_open
        from datetime import datetime, timezone
        with app.app_context():
            assert_period_open(datetime.now(timezone.utc), tenant_id=1)


# ---------------------------------------------------------------------------
# services/tax_service.py
# ---------------------------------------------------------------------------
class TestTaxServiceLogic:
    def test_calculate_sale_tax(self, app):
        from services.tax_service import TaxService
        with app.app_context():
            sale = type("S", (), {"amount_aed": Decimal("100"), "tax_rate": Decimal("5")})()
            result = TaxService.calculate_sale_tax(sale)
            assert result["strategy"] == "AE"
            assert result["tax_amount"] == Decimal("5")

    def test_calculate_purchase_tax(self, app):
        from services.tax_service import TaxService
        with app.app_context():
            purchase = type("P", (), {"amount_aed": Decimal("200"), "tax_rate": Decimal("5")})()
            result = TaxService.calculate_purchase_tax(purchase)
            assert result["strategy"] == "AE"
            assert result["tax_amount"] == Decimal("10")

    def test_vat_return(self, app):
        from services.tax_service import TaxService
        with app.app_context():
            result = TaxService.get_vat_return("2025-01-01", "2025-01-31")
            assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# services/commission_gl_service.py
# ---------------------------------------------------------------------------
class TestCommissionGLLogic:
    def test_no_entries_returns_none(self, app):
        from services.commission_gl_service import post_sale_commissions
        with app.app_context():
            sale = type("S", (), {"id": 999999, "tenant_id": 999999, "sale_number": "S-001", "branch_id": None})()
            assert post_sale_commissions(sale) is None


# ---------------------------------------------------------------------------
# services/donation_gl_service.py
# ---------------------------------------------------------------------------
class TestDonationGLLogic:
    def test_already_posted(self):
        from services.donation_gl_service import DonationGLService
        donation = type("D", (), {"gl_posted": True, "status": "completed", "amount_usd": 10, "tenant_id": 1})()
        assert DonationGLService.post_completed_donation(donation) is True

    def test_not_completed(self):
        from services.donation_gl_service import DonationGLService
        donation = type("D", (), {"gl_posted": False, "status": "pending", "amount_usd": 10, "tenant_id": 1})()
        assert DonationGLService.post_completed_donation(donation) is False

    def test_zero_amount(self):
        from services.donation_gl_service import DonationGLService
        donation = type("D", (), {"gl_posted": False, "status": "completed", "amount_usd": 0, "tenant_id": 1})()
        assert DonationGLService.post_completed_donation(donation) is False

    def test_no_tenant(self):
        from services.donation_gl_service import DonationGLService
        donation = type("D", (), {"id": 99, "gl_posted": False, "status": "completed", "amount_usd": 10, "tenant_id": None})()
        assert DonationGLService.post_completed_donation(donation) is False


# ---------------------------------------------------------------------------
# services/depreciation_service.py
# ---------------------------------------------------------------------------
class TestDepreciationService:
    def test_run_monthly_empty(self, app):
        from services.depreciation_service import DepreciationService
        with app.app_context():
            result = DepreciationService.run_monthly(tenant_id=999999)
            assert result == {"posted": 0, "skipped": 0, "errors": []}


# ---------------------------------------------------------------------------
# services/cheque_accounting_integration.py
# ---------------------------------------------------------------------------
class TestChequeAccountingGuards:
    def test_receive_wrong_type_raises(self, db_session, sample_tenant):
        from datetime import date
        from models import Cheque
        from services.cheque_accounting_integration import ChequeAccountingIntegration
        cheque = Cheque(
            tenant_id=sample_tenant.id,
            cheque_number="CH001",
            cheque_bank_number="BNK001",
            cheque_type="outgoing",
            bank_name="Bank",
            amount=Decimal("1000"),
            status="pending",
            issue_date=date.today(),
            due_date=date.today(),
        )
        db_session.add(cheque)
        db_session.commit()
        with pytest.raises(ValueError):
            ChequeAccountingIntegration.receive_cheque(cheque.id)

    def test_issue_wrong_type_raises(self, db_session, sample_tenant):
        from datetime import date
        from models import Cheque
        from services.cheque_accounting_integration import ChequeAccountingIntegration
        cheque = Cheque(
            tenant_id=sample_tenant.id,
            cheque_number="CH002",
            cheque_bank_number="BNK002",
            cheque_type="incoming",
            bank_name="Bank",
            amount=Decimal("1000"),
            status="pending",
            issue_date=date.today(),
            due_date=date.today(),
        )
        db_session.add(cheque)
        db_session.commit()
        with pytest.raises(ValueError):
            ChequeAccountingIntegration.issue_cheque(cheque.id)

    def test_clear_wrong_status_raises(self, db_session, sample_tenant):
        from datetime import date
        from models import Cheque
        from services.cheque_accounting_integration import ChequeAccountingIntegration
        cheque = Cheque(
            tenant_id=sample_tenant.id,
            cheque_number="CH003",
            cheque_bank_number="BNK003",
            cheque_type="incoming",
            bank_name="Bank",
            amount=Decimal("1000"),
            status="cleared",
            issue_date=date.today(),
            due_date=date.today(),
        )
        db_session.add(cheque)
        db_session.commit()
        with pytest.raises(ValueError):
            ChequeAccountingIntegration.clear_cheque(cheque.id)

    def test_summary_structure(self, db_session, sample_tenant):
        from datetime import date
        from models import Cheque
        from services.cheque_accounting_integration import ChequeAccountingIntegration
        cheque = Cheque(
            tenant_id=sample_tenant.id,
            cheque_number="CH004",
            cheque_bank_number="BNK004",
            cheque_type="incoming",
            bank_name="Bank",
            amount=Decimal("500"),
            status="pending",
            issue_date=date.today(),
            due_date=date.today(),
        )
        db_session.add(cheque)
        db_session.commit()
        summary = ChequeAccountingIntegration.get_cheque_accounting_summary(cheque.id)
        assert "cheque_info" in summary
        assert summary["cheque_info"]["id"] == cheque.id
        assert "journal_entries" in summary
        assert "account_impact" in summary


class TestCogsResolution:
    """Test COGS fallback chain like Odoo."""

    def test_resolve_cogs_raises_when_no_cost_data(self, app, db_session):
        from services.stock_service import StockService
        from models import Tenant, Product, Warehouse
        with app.app_context():
            tenant = Tenant(name='CGTest', name_ar='CGTest', slug='cgt', email='c@g.com', phone_1='050', country='AE', subscription_plan='basic')
            db_session.add(tenant)
            db_session.flush()
            product = Product(tenant_id=tenant.id, name='NoCost', current_stock=0, regular_price=Decimal('1'))
            db_session.add(product)
            db_session.flush()
            wh = Warehouse(tenant_id=tenant.id, name='WH', code='WH1')
            db_session.add(wh)
            db_session.flush()
            with pytest.raises(ValueError, match='لا يمكن تحديد تكلفة البضاعة المباعة'):
                StockService._resolve_cogs_unit_cost(product.id, wh.id, tenant.id, line_cost_price=None)

    def test_resolve_cogs_uses_cost_price_when_no_pwc(self, app, db_session):
        from services.stock_service import StockService
        from models import Tenant, Product, Warehouse
        with app.app_context():
            tenant = Tenant(name='CGTest2', name_ar='CGTest2', slug='cgt2', email='c2@g.com', phone_1='050', country='AE', subscription_plan='basic')
            db_session.add(tenant)
            db_session.flush()
            product = Product(tenant_id=tenant.id, name='WithCost', current_stock=0, cost_price=Decimal('150'), regular_price=Decimal('1'))
            db_session.add(product)
            db_session.flush()
            wh = Warehouse(tenant_id=tenant.id, name='WH', code='WH1')
            db_session.add(wh)
            db_session.flush()
            cost, source = StockService._resolve_cogs_unit_cost(product.id, wh.id, tenant.id, line_cost_price=Decimal('150'))
            assert cost == Decimal('150')
            assert source == 'cost_price'


class TestAzadPlatformFeeSettlement:
    """Test platform fee settlement summary and approval."""

    def test_get_accrued_summary_empty(self, app, db_session):
        from services.azad_platform_fee_service import AzadPlatformFeeService
        with app.app_context():
            result = AzadPlatformFeeService.get_accrued_summary(tenant_id=9999)
            assert result == []

    def test_get_settlement_report_empty(self, app, db_session):
        from services.azad_platform_fee_service import AzadPlatformFeeService
        with app.app_context():
            result = AzadPlatformFeeService.get_settlement_report(tenant_id=9999)
            assert result['count'] == 0
            assert result['total_fee_aed'] == Decimal('0')
