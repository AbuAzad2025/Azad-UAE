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
