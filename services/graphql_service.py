import graphene
from flask_login import current_user

from models import Sale, Customer, Product
from extensions import db
from utils.tenanting import tenant_query, assign_tenant_id


def _require_permission(permission_code):
    if not current_user.is_authenticated:
        raise PermissionError("Authentication required")
    if getattr(current_user, "is_owner", False):
        return
    if not current_user.has_permission(permission_code):
        raise PermissionError(f"Missing permission: {permission_code}")


class SaleType(graphene.ObjectType):
    id = graphene.Int()
    sale_number = graphene.String()
    customer_id = graphene.Int()
    total_amount = graphene.Float()
    amount_aed = graphene.Float()
    status = graphene.String()
    created_at = graphene.DateTime()


class CustomerType(graphene.ObjectType):
    id = graphene.Int()
    name = graphene.String()
    phone = graphene.String()
    email = graphene.String()
    address = graphene.String()
    balance = graphene.Float()


class ProductType(graphene.ObjectType):
    id = graphene.Int()
    name = graphene.String()
    part_number = graphene.String()
    regular_price = graphene.Float()
    cost_price = graphene.Float()
    current_stock = graphene.Int()
    is_active = graphene.Boolean()


class PaymentType(graphene.ObjectType):
    id = graphene.Int()
    amount = graphene.Float()
    currency = graphene.String()
    payment_method = graphene.String()
    reference_number = graphene.String()
    created_at = graphene.DateTime()


class Query(graphene.ObjectType):
    all_sales = graphene.List(SaleType, limit=graphene.Int(), offset=graphene.Int())
    sale = graphene.Field(SaleType, id=graphene.Int())

    all_customers = graphene.List(CustomerType, limit=graphene.Int())
    customer = graphene.Field(CustomerType, id=graphene.Int())

    all_products = graphene.List(ProductType, limit=graphene.Int())
    product = graphene.Field(ProductType, id=graphene.Int())

    @staticmethod
    def resolve_all_sales(info, limit=50, offset=0):
        _require_permission("manage_sales")
        sales = tenant_query(Sale).limit(limit).offset(offset).all()
        return [Query._convert_sale_to_type(sale) for sale in sales]

    @staticmethod
    def resolve_sale(info, record_id):
        _require_permission("manage_sales")
        sale = tenant_query(Sale).filter_by(id=record_id).first()
        return Query._convert_sale_to_type(sale) if sale else None

    @staticmethod
    def resolve_all_customers(info, limit=50):
        _require_permission("manage_customers")
        customers = tenant_query(Customer).limit(limit).all()
        return [Query._convert_customer_to_type(customer) for customer in customers]

    @staticmethod
    def resolve_customer(info, record_id):
        _require_permission("manage_customers")
        customer = tenant_query(Customer).filter_by(id=record_id).first()
        return Query._convert_customer_to_type(customer) if customer else None

    @staticmethod
    def resolve_all_products(info, limit=50):
        _require_permission("manage_products")
        products = tenant_query(Product).limit(limit).all()
        return [Query._convert_product_to_type(product) for product in products]

    @staticmethod
    def resolve_product(info, record_id):
        _require_permission("manage_products")
        product = tenant_query(Product).filter_by(id=record_id).first()
        return Query._convert_product_to_type(product) if product else None

    @staticmethod
    def _convert_sale_to_type(sale):
        return SaleType(
            id=sale.id,
            sale_number=sale.sale_number,
            customer_id=sale.customer_id,
            total_amount=float(sale.total_amount) if sale.total_amount else 0,
            amount_aed=float(sale.amount_aed) if sale.amount_aed else 0,
            status=sale.status,
            created_at=sale.created_at,
        )

    @staticmethod
    def _convert_customer_to_type(customer):
        return CustomerType(
            id=customer.id,
            name=customer.name,
            phone=customer.phone,
            email=customer.email,
            address=customer.address,
            balance=float(customer.balance) if customer.balance else 0,
        )

    @staticmethod
    def _convert_product_to_type(product):
        return ProductType(
            id=product.id,
            name=product.name,
            part_number=product.part_number,
            regular_price=float(product.regular_price) if product.regular_price else 0,
            cost_price=float(product.cost_price) if product.cost_price else 0,
            current_stock=product.current_stock,
            is_active=product.is_active,
        )


class CreateSale(graphene.Mutation):
    class Arguments:
        customer_id = graphene.Int(required=True)
        total_amount = graphene.Float(required=True)

    sale = graphene.Field(SaleType)
    success = graphene.Boolean()

    @staticmethod
    def mutate(info, customer_id, total_amount):
        _require_permission("manage_sales")
        from utils.helpers import generate_number
        from decimal import Decimal

        seller_id = current_user.id if current_user.is_authenticated else None
        if not seller_id:
            raise PermissionError("Authentication required")

        customer = tenant_query(Customer).filter_by(id=customer_id).first()
        if customer is None:
            raise ValueError("Customer not found or not accessible")

        sale = Sale(
            sale_number=generate_number("INV", Sale, "sale_number"),
            customer_id=customer.id,
            seller_id=seller_id,
            total_amount=Decimal(str(total_amount)),
            amount_aed=Decimal(str(total_amount)),
            status="pending",
        )
        assign_tenant_id(sale)
        db.session.add(sale)
        try:
            db.session.flush()
        except Exception:
            raise

        sale_type = SaleType(
            id=sale.id,
            sale_number=sale.sale_number,
            customer_id=sale.customer_id,
            total_amount=float(sale.total_amount),
            amount_aed=float(sale.amount_aed),
            status=sale.status,
            created_at=sale.created_at,
        )

        return CreateSale(sale=sale_type, success=True)


class Mutation(graphene.ObjectType):
    create_sale = CreateSale.Field()


def build_schema(*, allow_mutations=False):
    if allow_mutations:
        return graphene.Schema(query=Query, mutation=Mutation)
    return graphene.Schema(query=Query)


schema = build_schema(allow_mutations=False)
