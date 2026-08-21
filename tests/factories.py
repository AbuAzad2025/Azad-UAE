"""factory_boy factories for integration and unit tests.

Factories intentionally create their own tenant/role/branch records so they are
self-contained. Pass an existing tenant (or any parent) via keyword argument to
link factories together.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import factory
from factory import Faker, LazyAttribute, Sequence, SubFactory
from werkzeug.security import generate_password_hash

from extensions import db
from models import (
    Branch,
    Customer,
    GLAccount,
    Product,
    Purchase,
    PurchaseLine,
    Role,
    Sale,
    SaleLine,
    Supplier,
    Tenant,
    User,
    Warehouse,
)


class TenantFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Tenant
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "flush"

    name = Sequence(lambda n: f"Factory Tenant {n:04d}")
    name_ar = LazyAttribute(lambda o: f"مستأجر مصنع {o.name}")
    slug = Sequence(lambda n: f"factory-tenant-{n:04d}-{uuid.uuid4().hex[:6]}")
    email = Sequence(lambda n: f"factory-tenant-{n:04d}@example.com")
    phone_1 = "0500000000"
    country = "AE"
    subscription_plan = "basic"
    default_currency = "AED"
    base_currency = "AED"
    is_active = True
    is_suspended = False


class BranchFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Branch
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "flush"

    tenant = SubFactory(TenantFactory)
    tenant_id = LazyAttribute(lambda o: o.tenant.id)
    name = Sequence(lambda n: f"Main Branch {n:04d}")
    code = Sequence(lambda n: f"BR{n:04d}")
    is_active = True
    is_main = True


class WarehouseFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Warehouse
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "flush"

    tenant = SubFactory(TenantFactory)
    tenant_id = LazyAttribute(lambda o: o.tenant.id)
    branch = SubFactory(BranchFactory, tenant=factory.SelfAttribute("..tenant"))
    branch_id = LazyAttribute(lambda o: o.branch.id)
    name = Sequence(lambda n: f"Main Warehouse {n:04d}")
    name_ar = LazyAttribute(lambda o: f"المستودع الرئيسي {o.name}")
    code = Sequence(lambda n: f"WH{n:04d}")
    is_active = True
    is_main = True
    allow_negative_inventory = False


class RoleFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Role
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "flush"

    name = Sequence(lambda n: f"Factory Role {n:04d}")
    slug = Sequence(lambda n: f"factory-role-{n:04d}-{uuid.uuid4().hex[:6]}")
    is_active = True


class UserFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "flush"
        exclude = ("password",)

    tenant = SubFactory(TenantFactory)
    tenant_id = LazyAttribute(lambda o: o.tenant.id)
    role = SubFactory(RoleFactory)
    role_id = LazyAttribute(lambda o: o.role.id)
    username = Sequence(lambda n: f"factory-user-{n:04d}-{uuid.uuid4().hex[:6]}")
    email = Sequence(lambda n: f"factory-user-{n:04d}@example.com")
    full_name = Faker("name")
    password = factory.LazyAttribute(lambda _: "password123")
    password_hash = LazyAttribute(
        lambda o: generate_password_hash(o.password, method="pbkdf2:sha256:260000", salt_length=16)
    )
    is_active = True
    is_owner = False


class CustomerFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Customer
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "flush"

    tenant = SubFactory(TenantFactory)
    tenant_id = LazyAttribute(lambda o: o.tenant.id)
    name = Sequence(lambda n: f"Factory Customer {n:04d}")
    name_ar = LazyAttribute(lambda o: f"عميل مصنع {o.name}")
    customer_type = "regular"
    phone = Sequence(lambda n: f"050{n:08d}")
    email = Sequence(lambda n: f"factory-customer-{n:04d}@example.com")
    is_active = True
    balance = Decimal("0")


class SupplierFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Supplier
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "flush"

    tenant = SubFactory(TenantFactory)
    tenant_id = LazyAttribute(lambda o: o.tenant.id)
    name = Sequence(lambda n: f"Factory Supplier {n:04d}")
    name_ar = LazyAttribute(lambda o: f"مورد مصنع {o.name}")
    phone = Sequence(lambda n: f"055{n:08d}")
    email = Sequence(lambda n: f"factory-supplier-{n:04d}@example.com")
    is_active = True


class ProductFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Product
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "flush"

    tenant = SubFactory(TenantFactory)
    tenant_id = LazyAttribute(lambda o: o.tenant.id)
    name = Sequence(lambda n: f"Factory Product {n:04d}")
    name_ar = LazyAttribute(lambda o: f"منتج مصنع {o.name}")
    sku = Sequence(lambda n: f"SKU-FAC-{n:04d}-{uuid.uuid4().hex[:6]}")
    cost_price = Decimal("50.000")
    regular_price = Decimal("100.000")
    current_stock = Decimal("0")
    is_active = True
    unit = "piece"


class GLAccountFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = GLAccount
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "flush"

    tenant = SubFactory(TenantFactory)
    tenant_id = LazyAttribute(lambda o: o.tenant.id)
    code = Sequence(lambda n: f"ACC{n:04d}")
    name = Sequence(lambda n: f"Factory Account {n:04d}")
    name_ar = LazyAttribute(lambda o: f"حساب مصنع {o.name}")
    type = "asset"
    sub_type = "cash"
    currency = "AED"
    is_active = True
    is_header = False


class SaleFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Sale
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "flush"

    tenant = SubFactory(TenantFactory)
    tenant_id = LazyAttribute(lambda o: o.tenant.id)
    customer = SubFactory(CustomerFactory, tenant=factory.SelfAttribute("..tenant"))
    customer_id = LazyAttribute(lambda o: o.customer.id)
    seller = SubFactory(UserFactory, tenant=factory.SelfAttribute("..tenant"))
    seller_id = LazyAttribute(lambda o: o.seller.id)
    sale_number = Sequence(lambda n: f"SAL-FAC-{n:04d}")
    currency = "AED"
    exchange_rate = Decimal("1")
    total_amount = Decimal("0")
    amount = Decimal("0")
    amount_aed = Decimal("0")
    balance_due = Decimal("0")


class SaleLineFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = SaleLine
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "flush"

    tenant = SubFactory(TenantFactory)
    tenant_id = LazyAttribute(lambda o: o.tenant.id)
    sale = SubFactory(SaleFactory, tenant=factory.SelfAttribute("..tenant"))
    sale_id = LazyAttribute(lambda o: o.sale.id)
    product = SubFactory(ProductFactory, tenant=factory.SelfAttribute("..tenant"))
    product_id = LazyAttribute(lambda o: o.product.id)
    quantity = Decimal("1")
    unit_price = Decimal("100")
    discount_percent = Decimal("0")
    line_total = LazyAttribute(
        lambda o: (
            Decimal(str(o.quantity))
            * Decimal(str(o.unit_price))
            * (Decimal("1") - Decimal(str(o.discount_percent)) / Decimal("100"))
        ).quantize(Decimal("0.001"))
    )


class PurchaseFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = Purchase
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "flush"

    tenant = SubFactory(TenantFactory)
    tenant_id = LazyAttribute(lambda o: o.tenant.id)
    supplier = SubFactory(SupplierFactory, tenant=factory.SelfAttribute("..tenant"))
    supplier_id = LazyAttribute(lambda o: o.supplier.id)
    supplier_name = LazyAttribute(lambda o: o.supplier.name)
    user = SubFactory(UserFactory, tenant=factory.SelfAttribute("..tenant"))
    user_id = LazyAttribute(lambda o: o.user.id)
    purchase_number = Sequence(lambda n: f"PUR-FAC-{n:04d}")
    currency = "AED"
    exchange_rate = Decimal("1")
    total_amount = Decimal("0")
    amount = Decimal("0")
    amount_aed = Decimal("0")


class PurchaseLineFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = PurchaseLine
        sqlalchemy_session = db.session
        sqlalchemy_session_persistence = "flush"

    tenant = SubFactory(TenantFactory)
    tenant_id = LazyAttribute(lambda o: o.tenant.id)
    purchase = SubFactory(PurchaseFactory, tenant=factory.SelfAttribute("..tenant"))
    purchase_id = LazyAttribute(lambda o: o.purchase.id)
    product = SubFactory(ProductFactory, tenant=factory.SelfAttribute("..tenant"))
    product_id = LazyAttribute(lambda o: o.product.id)
    quantity = Decimal("1")
    unit_cost = Decimal("50")
    line_total = LazyAttribute(
        lambda o: (Decimal(str(o.quantity)) * Decimal(str(o.unit_cost))).quantize(Decimal("0.001"))
    )
