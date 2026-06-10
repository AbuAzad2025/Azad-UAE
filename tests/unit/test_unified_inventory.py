import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta


class TestSaleSalesRep:
    def test_sales_rep_id_column(self, sample_tenant, sample_user):
        from models.sale import Sale
        from models.customer import Customer
        from extensions import db
        customer = Customer(tenant_id=sample_tenant.id, name='Test', phone='123')
        db.session.add(customer)
        db.session.flush()
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number='S-001',
            customer_id=customer.id,
            seller_id=sample_user.id,
            sales_rep_id=sample_user.id,
            total_amount=100,
            amount=100,
            amount_aed=100,
        )
        db.session.add(sale)
        db.session.flush()
        assert sale.sales_rep_id == sample_user.id
        assert sale.sales_rep is not None

    def test_sale_amount_base_alias(self, sample_tenant, sample_user):
        from models.sale import Sale
        from models.customer import Customer
        from extensions import db
        customer = Customer(tenant_id=sample_tenant.id, name='Test', phone='123')
        db.session.add(customer)
        db.session.flush()
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number='S-002',
            customer_id=customer.id,
            seller_id=sample_user.id,
            total_amount=200,
            amount=200,
            amount_aed=200,
        )
        db.session.add(sale)
        db.session.flush()
        assert sale.amount_base == 200
        assert sale.base_amount == 200
        sale.amount_base = 300
        assert sale.amount_aed == 300


class TestPurchaseAmount:
    def test_purchase_amount_base_alias(self, sample_tenant, sample_user):
        from models.purchase import Purchase
        from extensions import db
        purchase = Purchase(
            tenant_id=sample_tenant.id,
            user_id=sample_user.id,
            purchase_number='P-001',
            supplier_name='Test Supplier',
            total_amount=100,
            amount=100,
            amount_aed=100,
        )
        db.session.add(purchase)
        db.session.flush()
        assert purchase.amount_base == 100
        purchase.amount_base = 150
        assert purchase.amount_aed == 150


class TestPartnerCommissionCurrency:
    def test_partner_commission_currency(self, sample_tenant):
        from models.partner_commission import PartnerCommissionEntry
        from extensions import db
        entry = PartnerCommissionEntry(
            tenant_id=sample_tenant.id,
            sale_id=1,
            partner_customer_id=1,
            percentage=10,
            base_amount_aed=100,
            commission_amount_aed=10,
            currency='AED',
        )
        db.session.add(entry)
        db.session.flush()
        assert entry.currency == 'AED'
        assert entry.commission_amount == 10


class TestSaleLineWarranty:
    def test_warranty_dates(self, sample_tenant, sample_user):
        from models.sale import Sale, SaleLine
        from models.customer import Customer
        from models.product import Product
        from extensions import db
        customer = Customer(tenant_id=sample_tenant.id, name='Test', phone='123')
        db.session.add(customer)
        db.session.flush()
        product = Product(tenant_id=sample_tenant.id, name='Test Product', regular_price=100)
        db.session.add(product)
        db.session.flush()
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number='S-003',
            customer_id=customer.id,
            seller_id=sample_user.id,
            total_amount=100,
            amount=100,
            amount_aed=100,
        )
        db.session.add(sale)
        db.session.flush()
        line = SaleLine(
            tenant_id=sample_tenant.id,
            sale_id=sale.id,
            product_id=product.id,
            quantity=1,
            unit_price=100,
            line_total=100,
            warranty_start_date=datetime.now(timezone.utc),
            warranty_end_date=datetime.now(timezone.utc) + timedelta(days=365),
        )
        db.session.add(line)
        db.session.flush()
        assert line.warranty_start_date is not None
        assert line.warranty_end_date is not None


class TestProductSerialImei:
    def test_imei_fields(self, sample_tenant):
        from models.product_serial import ProductSerial
        from models.product import Product
        from extensions import db
        product = Product(tenant_id=sample_tenant.id, name='Test Product', regular_price=100)
        db.session.add(product)
        db.session.flush()
        serial = ProductSerial(
            tenant_id=sample_tenant.id,
            product_id=product.id,
            serial_number='SN-001',
            imei1='123456789012345',
            imei2='543210987654321',
            model_number='MODEL-X',
            iccid='12345678901234567890',
        )
        db.session.add(serial)
        db.session.flush()
        assert serial.imei1 == '123456789012345'
        assert serial.imei2 == '543210987654321'
        assert serial.model_number == 'MODEL-X'
        assert serial.iccid == '12345678901234567890'


class TestIndustryService:
    def test_validate_industry_code(self):
        from services.industry_service import IndustryService
        assert IndustryService.validate_industry_code('general') is True
        assert IndustryService.validate_industry_code('invalid') is False

    def test_get_business_type_choices(self):
        from services.industry_service import IndustryService
        choices = IndustryService.get_business_type_choices()
        assert len(choices) > 0
        codes = [c[0] for c in choices]
        assert 'general' in codes
        assert 'automotive' in codes

    def test_get_core_fields(self, sample_tenant):
        from services.industry_service import IndustryService
        fields = IndustryService.get_core_fields()
        assert isinstance(fields, list)

    def test_get_fields_for_industry(self, sample_tenant):
        from services.industry_service import IndustryService
        fields = IndustryService.get_fields_for('automotive')
        assert isinstance(fields, list)

    def test_get_product_effective_industry(self, sample_tenant):
        from services.industry_service import IndustryService
        from models.product import Product
        from extensions import db
        product = Product(tenant_id=sample_tenant.id, name='Test', regular_price=50, industry='automotive')
        db.session.add(product)
        db.session.flush()
        assert IndustryService.get_product_effective_industry(product, sample_tenant) == 'automotive'


class TestPricingService:
    def test_get_price_regular(self, sample_tenant):
        from services.pricing_service import PricingService
        from models.product import Product
        from extensions import db
        product = Product(tenant_id=sample_tenant.id, name='Test', regular_price=50)
        db.session.add(product)
        db.session.flush()
        price = PricingService.get_price(product)
        assert price == 50

    def test_get_price_for_sale_line(self, sample_tenant):
        from services.pricing_service import PricingService
        from models.product import Product
        from extensions import db
        product = Product(tenant_id=sample_tenant.id, name='Test', regular_price=50)
        db.session.add(product)
        db.session.flush()
        result = PricingService.get_price_for_sale_line(product, 1, None)
        assert 'unit_price' in result
        assert 'commission_rate' in result


class TestCampaignService:
    def test_validate_coupon_no_match(self, sample_tenant):
        from services.campaign_service import CampaignService
        result = CampaignService.validate_coupon('INVALID', sample_tenant.id)
        assert result is None


class TestWarrantyService:
    def test_get_expiring_warranties_empty(self):
        from services.warranty_service import WarrantyService
        result = WarrantyService.get_expiring_warranties(days=30)
        assert isinstance(result, list)


class TestShipmentService:
    def test_get_shipments_for_sale_empty(self):
        from services.shipment_service import ShipmentService
        result = ShipmentService.get_shipments_for_sale(99999)
        assert isinstance(result, list)
        assert len(result) == 0


class TestProductImageService:
    def test_get_images_for_product_empty(self):
        from services.product_image_service import ProductImageService
        result = ProductImageService.get_images_for_product(99999)
        assert isinstance(result, list)
        assert len(result) == 0


class TestSerialTrackingService:
    def test_validate_imei_valid(self):
        from services.serial_tracking_service import SerialTrackingService
        assert SerialTrackingService.validate_imei('123456789012345') is True

    def test_validate_imei_invalid(self):
        from services.serial_tracking_service import SerialTrackingService
        assert SerialTrackingService.validate_imei('invalid') is False
        assert SerialTrackingService.validate_imei('123') is False
        assert SerialTrackingService.validate_imei(None) is False


class TestIndustryFieldsAPI:
    def _login(self, client, user):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

    def test_industry_fields_endpoint(self, client, sample_tenant, sample_user):
        from models.industry_field_definition import IndustryFieldDefinition
        from extensions import db
        field = IndustryFieldDefinition(
            industry_code='automotive',
            field_code='engine_capacity',
            field_name_ar='سعة المحرك',
            field_name_en='Engine Capacity',
            field_type='text',
            applies_to='product',
        )
        db.session.add(field)
        db.session.commit()
        self._login(client, sample_user)
        resp = client.get('/api/industry-fields?industry=automotive')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['industry'] == 'automotive'
        assert len(data['fields']) >= 1

    def test_industry_fields_empty(self, client, sample_user):
        self._login(client, sample_user)
        resp = client.get('/api/industry-fields?industry=general')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['industry'] == 'general'


class TestProductExtraFields:
    def test_extra_fields_saved_on_create(self, sample_tenant, sample_user):
        from models.product import Product
        from extensions import db
        product = Product(
            tenant_id=sample_tenant.id,
            name='Test Extra',
            sku='EXTRA-001',
            regular_price=100,
            cost_price=50,
            extra_fields={'engine_capacity': '2000cc', 'color': 'red'},
        )
        db.session.add(product)
        db.session.flush()
        assert product.extra_fields == {'engine_capacity': '2000cc', 'color': 'red'}

    def test_extra_fields_updated(self, sample_tenant, sample_user):
        from models.product import Product
        from extensions import db
        product = Product(
            tenant_id=sample_tenant.id,
            name='Test Extra',
            sku='EXTRA-002',
            regular_price=100,
            cost_price=50,
            extra_fields={'old': 'value'},
        )
        db.session.add(product)
        db.session.flush()
        product.extra_fields = {'new': 'value'}
        db.session.flush()
        assert product.extra_fields == {'new': 'value'}


class TestSaleServiceSalesRepId:
    def test_create_sale_sets_sales_rep_id(self, sample_tenant, sample_user):
        from models.sale import Sale
        from models.customer import Customer
        from extensions import db
        customer = Customer(tenant_id=sample_tenant.id, name='Test', phone='123')
        db.session.add(customer)
        db.session.flush()
        sale = Sale(
            tenant_id=sample_tenant.id,
            sale_number='S-TEST-001',
            customer_id=customer.id,
            seller_id=sample_user.id,
            sales_rep_id=sample_user.id,
            total_amount=100,
            amount=100,
            amount_aed=100,
        )
        db.session.add(sale)
        db.session.flush()
        assert sale.sales_rep_id == sample_user.id


class TestProductSerialWarehouse:
    def test_serial_warehouse_id_set_directly(self, sample_tenant):
        from models.product import Product
        from models.product_serial import ProductSerial
        from extensions import db
        product = Product(tenant_id=sample_tenant.id, name='SerialP', sku='SRL', regular_price=100, cost_price=50)
        db.session.add(product)
        db.session.flush()
        serial = ProductSerial(tenant_id=sample_tenant.id, product_id=product.id, serial_number='SN001', status='available', warehouse_id=5)
        db.session.add(serial)
        db.session.flush()
        assert serial.warehouse_id == 5
        serial.status = 'sold'
        serial.warehouse_id = 10
        db.session.flush()
        assert serial.warehouse_id == 10


class TestUnifiedInventoryRoutes:
    def _login(self, client, user):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True

    def test_campaigns_index(self, client, sample_user):
        from extensions import db
        sample_user.is_owner = True
        db.session.commit()
        self._login(client, sample_user)
        resp = client.get('/uinv/campaigns')
        assert resp.status_code == 200

    def test_warranty_index(self, client, sample_user):
        from extensions import db
        sample_user.is_owner = True
        db.session.commit()
        self._login(client, sample_user)
        resp = client.get('/uinv/warranty')
        assert resp.status_code == 200

    def test_shipments_index(self, client, sample_user):
        from extensions import db
        sample_user.is_owner = True
        db.session.commit()
        self._login(client, sample_user)
        resp = client.get('/uinv/shipments')
        assert resp.status_code == 200


class TestPurchaseAmountFix:
    def test_purchase_service_sets_amount(self, sample_tenant, sample_user, monkeypatch):
        from models.supplier import Supplier
        from models.product import Product
        from models.warehouse import Warehouse
        from services.purchase_service import PurchaseService
        from services.stock_service import StockService
        from extensions import db
        def _noop(movement):
            return None
        monkeypatch.setattr(StockService, '_post_adjustment_gl', _noop)
        monkeypatch.setattr('services.purchase_service.post_or_fail', lambda *a, **kw: None)
        supplier = Supplier(tenant_id=sample_tenant.id, name='Test Supplier', phone='123')
        db.session.add(supplier)
        wh = Warehouse(tenant_id=sample_tenant.id, name='Test WH', name_ar='مستودع', code='WH-PUR', is_main=True, is_active=True)
        db.session.add(wh)
        product = Product(tenant_id=sample_tenant.id, name='P', sku='PUR-1', regular_price=10, cost_price=5, current_stock=0)
        db.session.add(product)
        db.session.flush()
        purchase = PurchaseService.create_purchase(
            user=sample_user,
            supplier_data={'supplier_id': supplier.id, 'supplier_name': supplier.name, 'phone': '', 'email': ''},
            lines_data=[{'product_id': product.id, 'quantity': 5, 'unit_cost': 5, 'discount_percent': 0}],
            warehouse_id=wh.id,
            currency='AED',
        )
        assert purchase.amount is not None
        assert purchase.amount_aed is not None
        assert purchase.total_amount is not None

    def test_purchase_template_has_ils(self):
        html = open('templates/purchases/create.html', encoding='utf-8').read()
        assert 'currency_select' in html or 'ILS' in html
        assert 'macros/currency_options' in html or 'شيقل' in html


class TestExpenseAmountBase:
    def test_expense_amount_base_alias(self, sample_tenant, sample_user):
        from models.expense import Expense, ExpenseCategory
        from extensions import db
        cat = ExpenseCategory(tenant_id=sample_tenant.id, name='Test Cat', name_ar='اختبار', gl_account_code='6100')
        db.session.add(cat)
        db.session.flush()
        expense = Expense(
            tenant_id=sample_tenant.id,
            expense_number='EXP-001',
            category_id=cat.id,
            description='Test',
            amount=100,
            currency='AED',
            exchange_rate=1,
            amount_aed=100,
            payment_method='cash',
            user_id=sample_user.id,
        )
        db.session.add(expense)
        db.session.flush()
        assert expense.amount_base == 100
        expense.amount_base = 200
        assert expense.amount_aed == 200

    def test_expense_create_template_has_ils(self):
        html = open('templates/expenses/create.html', encoding='utf-8').read()
        assert 'currency_select' in html or 'ILS' in html
        assert 'macros/currency_options' in html or 'شيقل' in html

    def test_expense_edit_template_has_ils(self):
        html = open('templates/expenses/edit.html', encoding='utf-8').read()
        assert 'currency_select' in html or 'ILS' in html
        assert 'macros/currency_options' in html or 'شيقل' in html


class TestCurrencyConstants:
    def test_jod_in_currencies(self):
        from utils.constants import CURRENCIES
        codes = [c[0] for c in CURRENCIES]
        assert 'JOD' in codes
        jod = next(c[1] for c in CURRENCIES if c[0] == 'JOD')
        assert 'دينار أردني' in jod['ar']

    def test_currency_macro_template_exists(self):
        html = open('templates/macros/currency_options.html', encoding='utf-8').read()
        assert 'JOD' in html
        assert 'AED' in html
        assert 'USD' in html
        assert 'ILS' in html
        assert 'SAR' in html
        assert 'currency_select' in html


class TestPurchaseSerialTracking:
    def test_serial_created_on_purchase(self, sample_tenant, sample_user, monkeypatch):
        from models.supplier import Supplier
        from models.product import Product
        from models.warehouse import Warehouse
        from models.product_serial import ProductSerial
        from services.purchase_service import PurchaseService
        from services.stock_service import StockService
        from extensions import db
        def _noop(movement):
            return None
        monkeypatch.setattr(StockService, '_post_adjustment_gl', _noop)
        monkeypatch.setattr('services.purchase_service.post_or_fail', lambda *a, **kw: None)
        supplier = Supplier(tenant_id=sample_tenant.id, name='Test Supplier', phone='123')
        db.session.add(supplier)
        wh = Warehouse(tenant_id=sample_tenant.id, name='Test WH', name_ar='مستودع', code='WH-PUR2', is_main=True, is_active=True)
        db.session.add(wh)
        product = Product(tenant_id=sample_tenant.id, name='SerialP', sku='SRL-PUR', regular_price=100, cost_price=50, has_serial_number=True, warranty_days=30, current_stock=0)
        db.session.add(product)
        db.session.flush()
        purchase = PurchaseService.create_purchase(
            user=sample_user,
            supplier_data={'supplier_id': supplier.id, 'supplier_name': supplier.name, 'phone': '', 'email': ''},
            lines_data=[{'product_id': product.id, 'quantity': 2, 'unit_cost': 50, 'discount_percent': 0, 'serials': ['SN-001', 'SN-002']}],
            warehouse_id=wh.id,
            currency='AED',
        )
        serials = ProductSerial.query.filter_by(purchase_line_id=purchase.lines[0].id).all()
        assert len(serials) == 2
        assert all(s.status == 'available' for s in serials)
        assert all(s.warehouse_id == wh.id for s in serials)


class TestGlPostingPreservesOriginalAmount:
    def test_post_entry_preserves_original_currency_amount(self, sample_tenant, monkeypatch):
        from services.gl_service import GLService
        captured_lines = []
        def fake_create_journal_entry(date, description, lines, **kw):
            captured_lines.extend(lines)
            class FakeEntry:
                pass
            return FakeEntry()
        monkeypatch.setattr(GLService, 'create_journal_entry', fake_create_journal_entry)
        GLService.post_entry(
            [{'account': '1000', 'debit': 100, 'credit': 0, 'description': 'test'}],
            description='Test Entry',
            currency='USD',
            exchange_rate=3.67,
            tenant_id=sample_tenant.id,
        )
        assert len(captured_lines) == 1
        line = captured_lines[0]
        assert line['original_debit'] == 100
        assert line['original_credit'] == 0
        assert line['debit'] == 367
        assert line['credit'] == 0


class TestTenantCurrencyMandatory:
    def test_tenant_create_template_uses_currency_macro(self):
        html = open('templates/owner/tenant_create.html', encoding='utf-8').read()
        assert 'currency_select' in html or 'default_currency' in html
        assert 'AED' in html


class TestReportsTenantScoping:
    def test_reports_uses_tenant_query(self):
        code = open('routes/reports.py', encoding='utf-8').read()
        assert "tenant_query(Product)" in code
        assert "tenant_query(SaleLine)" in code

    def test_reports_partners_uses_tenant_filters(self):
        code = open('routes/reports.py', encoding='utf-8').read()
        assert "partner_products = tenant_query(Product)" in code
        assert "merchant_products = tenant_query(Product)" in code

    def test_reports_partners_financials_uses_tenant_filter(self):
        code = open('routes/reports.py', encoding='utf-8').read()
        assert "paid_query.filter(Payment.tenant_id == tenant_id)" in code
        assert "receipts_query.filter(Receipt.tenant_id == tenant_id)" in code

    def test_reports_sales_uses_tenant_query(self):
        code = open('routes/reports.py', encoding='utf-8').read()
        assert "tenant_query(Sale).filter_by(status='confirmed')" in code

    def test_reports_purchases_uses_tenant_query(self):
        code = open('routes/reports.py', encoding='utf-8').read()
        assert "tenant_query(Purchase).filter_by(status='confirmed')" in code

    def test_reports_inventory_uses_tenant_query(self):
        code = open('routes/reports.py', encoding='utf-8').read()
        assert "tenant_query(Warehouse)" in code
        assert "tenant_query(Product).filter_by(is_active=True)" in code

    def test_reports_receivables_uses_tenant_query(self):
        code = open('routes/reports.py', encoding='utf-8').read()
        assert "tenant_query(Sale).filter(" in code

    def test_reports_entity_fragment_uses_tenant_scoping(self):
        code = open('routes/reports.py', encoding='utf-8').read()
        assert "tenant_get_or_404(Supplier, id)" in code
        assert "tenant_get_or_404(Customer, id)" in code

    def test_reports_top_selling_uses_tenant_filter(self):
        code = open('routes/reports.py', encoding='utf-8').read()
        assert "query.filter(Sale.tenant_id == tenant_id)" in code

    def test_reports_treasury_uses_tenant_scoping(self):
        code = open('routes/treasury.py', encoding='utf-8').read()
        assert "tenant_id=tenant_id" in code
        assert "TaxService.get_vat_return" in code


class TestPosIntegration:
    def test_pos_route_exists(self):
        code = open('routes/pos.py', encoding='utf-8').read()
        assert "pos_bp" in code
        assert "/api/checkout" in code
        assert "/api/products" in code

    def test_pos_uses_sale_service(self):
        code = open('routes/pos.py', encoding='utf-8').read()
        assert "SaleService.create_sale" in code

    def test_pos_uses_tenant_get_for_customer(self):
        code = open('routes/pos.py', encoding='utf-8').read()
        assert "tenant_get(Customer" in code

    def test_pos_uses_tenant_get_for_product(self):
        code = open('routes/pos.py', encoding='utf-8').read()
        assert "tenant_get(Product" in code

    def test_pos_ensure_warehouse_access(self):
        code = open('routes/pos.py', encoding='utf-8').read()
        assert "ensure_warehouse_access" in code

    def test_pos_helpers_use_tenant_query(self):
        code = open('utils/pos_helpers.py', encoding='utf-8').read()
        assert "tenant_query" in code
        assert "get_active_tenant_id" in code

    def test_pos_template_uses_currency_macro(self):
        html = open('templates/pos/index.html', encoding='utf-8').read()
        assert 'currency_select' in html
        assert 'macros/currency_options' in html

    def test_pos_before_request_checks_tenant_enable_pos(self):
        code = open('routes/pos.py', encoding='utf-8').read()
        assert "tenant.enable_pos" in code
        assert "enable_pos" in code


class TestEnumsConsistency:
    def test_expense_statuses_constant_exists(self):
        from utils.constants import EXPENSE_STATUSES
        assert EXPENSE_STATUSES is not None
        codes = [s[0] for s in EXPENSE_STATUSES]
        assert 'confirmed' in codes
        assert 'cancelled' in codes

    def test_normalize_payment_method_alias_bank(self):
        from utils.constants import normalize_payment_method_code
        assert normalize_payment_method_code('bank') == 'bank_transfer'
        assert normalize_payment_method_code('BANK') == 'bank_transfer'
        assert normalize_payment_method_code('cash') == 'cash'
        assert normalize_payment_method_code(None) is None

    def test_payment_model_imports_normalize(self):
        code = open('models/payment.py', encoding='utf-8').read()
        assert 'normalize_payment_method_code' in code

    def test_payment_get_method_display_uses_normalize(self):
        code = open('models/payment.py', encoding='utf-8').read()
        assert code.count('canonical = normalize_payment_method_code') == 2


class TestBankCashGlIntegration:
    def test_cash_box_has_tenant_id(self):
        code = open('models/cash_box.py', encoding='utf-8').read()
        assert "tenant_id = db.Column" in code
        assert "db.ForeignKey('tenants.id'" in code

    def test_cash_box_has_gl_account_link(self):
        code = open('models/cash_box.py', encoding='utf-8').read()
        assert "gl_account_id" in code
        assert "gl_account = db.relationship('GLAccount'" in code

    def test_gl_account_has_tenant_unique_constraint(self):
        code = open('models/gl.py', encoding='utf-8').read()
        assert "db.UniqueConstraint('tenant_id', 'code'" in code

    def test_gl_account_has_liquidity_kind(self):
        code = open('models/gl.py', encoding='utf-8').read()
        assert "liquidity_kind = db.Column" in code

    def test_bank_reconciliation_model_has_tenant_id(self):
        code = open('models/bank_reconciliation.py', encoding='utf-8').read()
        assert "tenant_id = db.Column" in code
        assert "db.ForeignKey('tenants.id'" in code

    def test_bank_reconciliation_service_uses_tenant_get_or_404(self):
        code = open('services/bank_reconciliation_service.py', encoding='utf-8').read()
        assert 'tenant_get_or_404(GLAccount' in code

    def test_bank_reconciliation_auto_populate_uses_tenant_filter(self):
        code = open('services/bank_reconciliation_service.py', encoding='utf-8').read()
        assert "tid = getattr(reconciliation, 'tenant_id'" in code
        assert "in_q.filter(Cheque.tenant_id == tid)" in code
        assert "out_q.filter(Cheque.tenant_id == tid)" in code

    def test_treasury_service_filters_cashbox_by_tenant(self):
        code = open('services/treasury_service.py', encoding='utf-8').read()
        assert "CashBox.query.filter_by(tenant_id=tenant_id" in code

    def test_treasury_service_filters_gl_fallback_by_tenant(self):
        code = open('services/treasury_service.py', encoding='utf-8').read()
        assert "GLAccount.tenant_id == tenant_id" in code

    def test_treasury_service_filters_cheques_by_tenant(self):
        code = open('services/treasury_service.py', encoding='utf-8').read()
        assert "Cheque.tenant_id == tenant_id" in code

    def test_treasury_service_reconciliation_joins_tenant(self):
        code = open('services/treasury_service.py', encoding='utf-8').read()
        assert "GLAccount.tenant_id == tenant_id" in code
        assert "BankReconciliation.query" in code

    def test_gl_posting_accepts_tenant_id(self):
        code = open('services/gl_posting.py', encoding='utf-8').read()
        assert "tenant_id=None" in code
        assert "tenant_id=tenant_id" in code


class TestChequeModule:
    def test_cheque_model_has_tenant_id(self):
        code = open('models/cheque.py', encoding='utf-8').read()
        assert "tenant_id = db.Column" in code
        assert "db.ForeignKey('tenants.id'" in code

    def test_cheque_model_no_duplicate_type_ar(self):
        code = open('models/cheque.py', encoding='utf-8').read()
        assert code.count("def type_ar") == 0
        assert "def cheque_type_ar" in code

    def test_cheque_model_to_dict_uses_cheque_type_ar(self):
        code = open('models/cheque.py', encoding='utf-8').read()
        assert "'type_ar': self.cheque_type_ar" in code

    def test_cheque_static_methods_accept_tenant_id(self):
        code = open('models/cheque.py', encoding='utf-8').read()
        assert "def get_incoming_cheques(tenant_id=None" in code
        assert "def get_outgoing_cheques(tenant_id=None" in code
        assert "def get_due_soon_cheques(tenant_id=None" in code
        assert "def get_overdue_cheques(tenant_id=None" in code
        assert "def update_all_statuses(tenant_id=None" in code
        assert "def get_statistics(tenant_id=None" in code

    def test_cheque_static_methods_filter_by_tenant(self):
        code = open('models/cheque.py', encoding='utf-8').read()
        assert code.count("query.filter(Cheque.tenant_id == tenant_id)") >= 4

    def test_cheque_update_all_statuses_no_db_commit(self):
        code = open('models/cheque.py', encoding='utf-8').read()
        assert "db.session.commit()" not in code.split("def update_all_statuses")[1].split("def ")[0]

    def test_cheque_service_clear_uses_tenant_filter(self):
        code = open('services/cheque_service.py', encoding='utf-8').read()
        assert "pmt_q.filter(Payment.tenant_id == tid)" in code
        assert "rcpt_q.filter(Receipt.tenant_id == tid)" in code

    def test_cheque_service_bounce_uses_tenant_filter(self):
        code = open('services/cheque_service.py', encoding='utf-8').read()
        clear_section = code.split("def process_cheque_clear")[1].split("def _create_bounce_journal_entry")[0]
        bounce_section = code.split("def process_cheque_bounce")[1].split("def _create_cancel_journal_entry")[0]
        assert "pmt_q.filter(Payment.tenant_id == tid)" in clear_section
        assert "rcpt_q.filter(Receipt.tenant_id == tid)" in clear_section
        assert "pmt_q.filter(Payment.tenant_id == tid)" in bounce_section
        assert "rcpt_q.filter(Receipt.tenant_id == tid)" in bounce_section

    def test_cheque_service_type_ar_references_updated(self):
        code = open('services/cheque_service.py', encoding='utf-8').read()
        assert "cheque.type_ar" not in code
        assert "cheque.cheque_type_ar" in code

    def test_cheque_routes_ensure_scope_checks_tenant(self):
        code = open('routes/cheques.py', encoding='utf-8').read()
        assert "get_active_tenant_id(current_user)" in code.split("def _ensure_cheque_scope")[1].split("def _resolve_transaction_rate")[0]

    def test_cheque_routes_pass_tenant_to_statistics(self):
        code = open('routes/cheques.py', encoding='utf-8').read()
        assert code.count("get_statistics(tenant_id=tid") >= 4

    def test_cheque_routes_pass_tenant_to_due_soon(self):
        code = open('routes/cheques.py', encoding='utf-8').read()
        assert "get_due_soon_cheques(tenant_id=tid" in code

    def test_cheque_routes_pass_tenant_to_overdue(self):
        code = open('routes/cheques.py', encoding='utf-8').read()
        assert "get_overdue_cheques(tenant_id=tid" in code

    def test_cheque_routes_pass_tenant_to_update_statuses(self):
        code = open('routes/cheques.py', encoding='utf-8').read()
        assert code.count("update_all_statuses(tenant_id=tid") >= 6

    def test_cheque_routes_bounced_query_uses_scoped(self):
        code = open('routes/cheques.py', encoding='utf-8').read()
        assert "_scoped_cheques_query().filter_by(status='bounced')" in code

    def test_cheque_routes_archived_query_uses_scoped(self):
        code = open('routes/cheques.py', encoding='utf-8').read()
        assert "_scoped_cheques_query().filter_by(is_active=False)" in code

    def test_cheque_routes_no_raw_get_or_404(self):
        code = open('routes/cheques.py', encoding='utf-8').read()
        assert "Cheque.query.get_or_404" not in code

    def test_cheque_routes_uses_scoped_get_or_404(self):
        code = open('routes/cheques.py', encoding='utf-8').read()
        assert "def _get_cheque_or_404" in code
        assert "tenant_get_or_404(Cheque" in code

    def test_cheque_routes_view_no_commit(self):
        code = open('routes/cheques.py', encoding='utf-8').read()
        view_body = code.split("def view(id):")[1].split("def edit(id):")[0]
        assert "db.session.commit()" not in view_body


class TestBranchesRoutes:
    def test_branches_uses_tenant_get_or_404(self):
        code = open('routes/branches.py', encoding='utf-8').read()
        assert "tenant_get_or_404(Branch, id)" in code

    def test_branches_no_manual_tenant_check_after_get(self):
        code = open('routes/branches.py', encoding='utf-8').read()
        assert "branch.tenant_id != tenant_id" not in code


class TestDatabaseSchemaAudit:
    def test_tables_match_models(self, app):
        from extensions import db
        from sqlalchemy import inspect
        with app.app_context():
            inspector = inspect(db.engine)
            db_tables = set(inspector.get_table_names())
            model_tables = set(db.metadata.tables.keys())
            extra_in_db = db_tables - model_tables
            missing_in_db = model_tables - db_tables
            assert missing_in_db == set(), f'Tables in models but missing in DB: {missing_in_db}'
            assert extra_in_db <= {'alembic_version'}, f'Unexpected extra tables in DB: {extra_in_db}'

    def test_no_missing_columns(self, app):
        from extensions import db
        from sqlalchemy import inspect
        with app.app_context():
            inspector = inspect(db.engine)
            issues = []
            for table_name in db.metadata.tables:
                if not inspector.has_table(table_name):
                    issues.append(f'MISSING TABLE: {table_name}')
                    continue
                db_cols = {c['name'] for c in inspector.get_columns(table_name)}
                model_cols = {c.name for c in db.metadata.tables[table_name].columns}
                missing = model_cols - db_cols
                for col in missing:
                    issues.append(f'MISSING COLUMN: {table_name}.{col}')
            assert issues == [], f'Schema issues: {issues}'

    def test_no_broken_foreign_keys(self, app):
        from extensions import db
        from sqlalchemy import inspect
        with app.app_context():
            inspector = inspect(db.engine)
            db_tables = set(inspector.get_table_names())
            issues = []
            for table_name in db.metadata.tables:
                if not inspector.has_table(table_name):
                    continue
                for fk in db.metadata.tables[table_name].foreign_keys:
                    if fk.column.table.name not in db_tables:
                        issues.append(f'BROKEN FK: {table_name}.{fk.parent.name} -> {fk.column.table.name}')
            assert issues == [], f'Broken FKs: {issues}'

    def test_no_backref_conflicts(self, app):
        from extensions import db
        with app.app_context():
            backrefs = {}
            issues = []
            for cls in db.Model.registry._class_registry.values():
                if not hasattr(cls, '__mapper__'):
                    continue
                for rel in cls.__mapper__.relationships:
                    backref_name = None
                    if rel.backref:
                        if isinstance(rel.backref, str):
                            backref_name = rel.backref
                        elif isinstance(rel.backref, dict):
                            backref_name = rel.backref.get('name')
                    if backref_name:
                        key = (rel.target.name, backref_name)
                        if key in backrefs:
                            issues.append(f'BACKREF CONFLICT: {backrefs[key]} and {cls.__name__}.{rel.key}')
                        else:
                            backrefs[key] = f'{cls.__name__}.{rel.key}'
            assert issues == [], f'Backref conflicts: {issues}'
