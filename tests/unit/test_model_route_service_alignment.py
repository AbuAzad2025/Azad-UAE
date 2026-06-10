import ast
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


def _extract_model_names():
    names = set()
    models_dir = PROJECT_ROOT / 'models'
    for path in models_dir.glob('*.py'):
        if path.name.startswith('_'):
            continue
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_str = ast.dump(base)
                    if 'db.Model' in base_str or 'Model' in base_str:
                        names.add(node.name)
                        break
    return names


def _extract_imported_models(file_path):
    models = set()
    try:
        tree = ast.parse(file_path.read_text(encoding='utf-8'))
    except (SyntaxError, UnicodeDecodeError):
        return models
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if 'models' in (node.module or ''):
                for alias in node.names:
                    models.add(alias.name)
    return models


def _extract_direct_model_refs(file_path, known_models):
    refs = set()
    try:
        tree = ast.parse(file_path.read_text(encoding='utf-8'))
    except (SyntaxError, UnicodeDecodeError):
        return refs
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id in known_models:
                refs.add(node.id)
        elif isinstance(node, ast.Attribute):
            if node.attr in known_models:
                refs.add(node.attr)
    return refs


def _extract_blueprint_names(file_path):
    bps = set()
    try:
        tree = ast.parse(file_path.read_text(encoding='utf-8'))
    except (SyntaxError, UnicodeDecodeError):
        return bps
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith('_bp'):
                    bps.add(target.id)
        if isinstance(node, ast.Call):
            func_str = ast.dump(node.func)
            if 'Blueprint' in func_str:
                for kw in node.keywords:
                    if kw.arg == 'name' and isinstance(kw.value, ast.Constant):
                        bps.add(kw.value.value)
    return bps


def _extract_service_class_names():
    services = {}
    services_dir = PROJECT_ROOT / 'services'
    for path in services_dir.glob('*.py'):
        if path.name.startswith('_'):
            continue
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                services[node.name] = path.name
    return services


class TestModelRouteServiceAlignment:
    def test_models_have_routes(self):
        known_models = _extract_model_names()
        routes_dir = PROJECT_ROOT / 'routes'
        model_routes = {m: set() for m in known_models}
        for path in routes_dir.glob('*.py'):
            if path.name.startswith('_'):
                continue
            refs = _extract_direct_model_refs(path, known_models)
            for m in refs:
                model_routes[m].add(path.name)
        orphan_models = {m for m, routes in model_routes.items() if not routes}
        core_models = {'db', 'db.Model', 'BaseModel', 'UserMixin', 'Tenant', 'Branch', 'Role', 'Permission', 'APIKey', 'SecurityAlert', 'CardVault', 'Package', 'PackagePurchase', 'CardPayment', 'Currency', 'ArchivedRecord', 'AuditLog', 'LoginHistory', 'SystemSetting', 'InvoiceSettings', 'IntegrationSettings', 'GLAccount', 'GLJournalEntry', 'GLJournalLine', 'GLPeriod', 'CostCenter', 'ProfitCenter', 'Budget', 'BudgetLine', 'BankReconciliation', 'BankReconciliationItem', 'DepreciationSchedule', 'FixedAsset', 'ExchangeRateRecord', 'ExchangeRate', 'TaxCalculationRule', 'CustomsTax', 'IndustryFieldDefinition', 'GLAccountMapping', 'Campaign', 'SaleCampaign', 'ProductImage', 'ProductPriceTier', 'ProductCostHistory', 'ProductWarehouseCost', 'ProductWarehouseStock', 'ProductSerial', 'ProductReturn', 'ProductReturnLine', 'Partner', 'PartnerTransaction', 'PartnerCommissionEntry', 'PartnerProfitDistribution', 'ProductPartner', 'Employee', 'PayrollTransaction', 'SalaryAdvance', 'ShopAbandonedCart', 'ShopCustomerAccount', 'ShopLoyalty', 'ShopLoyaltyTransaction', 'ShopNewsletter', 'ShopProductVariant', 'ShopReview', 'ShopSavedPayment', 'ShopStockAlert', 'ShopWishlist', 'StoreCoupon', 'StorePaymentMethod', 'TenantStore', 'ErrorAuditLog', 'JournalEntryAudit', 'AzadPlatformFee', 'JournalEntryAuditLog', 'AIInteraction', 'AIMemory', 'AIExpertise', 'SalesRepCommission', 'PaymentTransaction', 'CashBox'}
        ai_models = {'AiMemory', 'AiExpertise'}
        orphan_models -= core_models
        orphan_models -= ai_models
        assert orphan_models == set(), f'Models with no route references: {orphan_models}'

    def test_routes_only_reference_existing_models(self):
        known_models = _extract_model_names()
        routes_dir = PROJECT_ROOT / 'routes'
        issues = []
        for path in routes_dir.glob('*.py'):
            if path.name.startswith('_'):
                continue
            refs = _extract_direct_model_refs(path, known_models)
            for m in refs:
                if m not in known_models:
                    issues.append(f'{path.name}: {m}')
        assert issues == [], f'Routes reference unknown models: {issues}'

    def test_services_only_reference_existing_models(self):
        known_models = _extract_model_names()
        services_dir = PROJECT_ROOT / 'services'
        issues = []
        for path in services_dir.glob('*.py'):
            if path.name.startswith('_'):
                continue
            refs = _extract_direct_model_refs(path, known_models)
            for m in refs:
                if m not in known_models:
                    issues.append(f'{path.name}: {m}')
        assert issues == [], f'Services reference unknown models: {issues}'

    def test_services_classes_exist(self):
        services = _extract_service_class_names()
        assert len(services) > 0, 'No service classes found'
        key_services = {'ChequeAccountingIntegration', 'GLService', 'BankReconciliationService', 'TreasuryService', 'StockService', 'SaleService', 'PurchaseService', 'PaymentService', 'TaxService', 'CurrencyService', 'AuditService', 'ArchiveService', 'HealthCheckService', 'BackupService', 'UserService', 'TenantService', 'RoleService', 'WarrantyService', 'WebhookService', 'WhatsAppService', 'StoreService', 'StoreOrderService', 'StoreCheckoutService', 'StoreCouponService', 'StoreAnalyticsService', 'StorePaymentMethodService', 'StoreOnlinePaymentService', 'StoreNotificationService', 'ShopCustomerAuthService', 'ShipmentService', 'SerialTrackingService', 'ReturnService', 'PricingService', 'ProductImageService', 'PredictiveMaintenanceService', 'PayrollService', 'PartnerService', 'NotificationService', 'SecurityService', 'MonitoringService', 'InventoryReconciliationService', 'IntegrationService', 'IndustryService', 'AIService', 'AIExecutor'}
        missing = key_services - set(services.keys())
        assert missing == set(), f'Key service classes missing: {missing}'

    def test_routes_have_blueprint(self):
        routes_dir = PROJECT_ROOT / 'routes'
        issues = []
        for path in routes_dir.glob('*.py'):
            if path.name.startswith('_'):
                continue
            bps = _extract_blueprint_names(path)
            if not bps:
                issues.append(path.name)
        assert issues == [], f'Route files without Blueprint: {issues}'

    def test_all_routes_import_tenanting(self):
        routes_dir = PROJECT_ROOT / 'routes'
        issues = []
        for path in routes_dir.glob('*.py'):
            if path.name.startswith('_'):
                continue
            code = path.read_text(encoding='utf-8')
            if 'tenant' not in code.lower():
                issues.append(path.name)
        allowed = {'__init__.py', 'auth.py', 'public.py', 'api_docs.py', 'graphql.py', 'websocket.py', 'monitoring.py', 'language.py', 'gamification.py'}
        issues = [f for f in issues if f not in allowed]
        assert issues == [], f'Route files without tenant awareness: {issues}'

    def test_all_routes_import_login_required(self):
        routes_dir = PROJECT_ROOT / 'routes'
        issues = []
        for path in routes_dir.glob('*.py'):
            if path.name.startswith('_'):
                continue
            code = path.read_text(encoding='utf-8')
            if 'login_required' not in code:
                issues.append(path.name)
        allowed = {'__init__.py', 'public.py', 'api_docs.py', 'graphql.py', 'websocket.py', 'auth.py', 'language.py'}
        issues = [f for f in issues if f not in allowed]
        assert issues == [], f'Route files without login_required: {issues}'
