"""Cov5: product_service — helper arcs to 100%."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_category_helpers(db_session, sample_tenant):
    from services.product_service import ProductService

    cat = ProductService.create_category("Cat5", tenant_id=sample_tenant.id)
    db_session.flush()
    assert cat.tenant_id == sample_tenant.id
    cat2 = ProductService.create_category("NoTenant")
    assert cat2.tenant_id is None
    db_session.expunge(cat2)
    db_session.flush()

    assert ProductService.category_name_taken(sample_tenant.id, "cat5") is True
    assert ProductService.category_name_taken(sample_tenant.id, "cat5", exclude_id=cat.id) is False
    assert ProductService.category_name_taken(sample_tenant.id, "missing") is False
    found = ProductService.find_category_name_conflict(sample_tenant.id, "CAT5")
    assert found.id == cat.id
    assert ProductService.find_category_name_conflict(sample_tenant.id, "CAT5", exclude_id=cat.id) is None
    assert ProductService.find_category_by_name(sample_tenant.id, "cat5").id == cat.id
    assert ProductService.find_category_by_name(sample_tenant.id, "nope") is None
    assert ProductService.get_active_category(cat.id, sample_tenant.id).id == cat.id
    assert ProductService.get_active_category(999999999, sample_tenant.id) is None
    ordered = ProductService.list_active_categories(sample_tenant.id, ordered=True)
    assert any(c.id == cat.id for c in ordered)
    unordered = ProductService.list_active_categories(sample_tenant.id)
    assert any(c.id == cat.id for c in unordered)


def test_delete_product_branches(db_session, sample_tenant, sample_product):
    from models import Product
    from services.product_service import ProductService

    ProductService.delete_product(sample_product, has_sales=True)
    assert sample_product.is_active is False
    db_session.flush()
    p2 = Product(
        tenant_id=sample_tenant.id,
        name="Gone",
        sku="SKU-COV5-DEL",
        cost_price=Decimal("1"),
        regular_price=Decimal("2"),
    )
    db_session.add(p2)
    db_session.flush()
    pid = p2.id
    ProductService.delete_product(p2)
    db_session.flush()
    assert Product.query.get(pid) is None


def test_price_tier_helpers(db_session, sample_tenant, sample_product):
    from services.product_service import ProductService

    t = ProductService.create_price_tier(sample_product.id, "T5", Decimal("9"), tenant_id=sample_tenant.id)
    db_session.flush()
    assert t.tenant_id == sample_tenant.id
    t2 = ProductService.create_price_tier(sample_product.id, "T5B", Decimal("8"))
    assert t2.tenant_id is None
    db_session.expunge(t2)
    db_session.flush()
    assert ProductService.get_price_tier(sample_product.id, "T5").id == t.id
    assert ProductService.get_price_tier(sample_product.id, "NOPE") is None


def test_product_lookups(db_session, sample_tenant, sample_product, sample_customer):
    from services.product_service import ProductService

    assert ProductService.get_tenant_product(sample_product.id, sample_tenant.id).id == sample_product.id
    assert ProductService.get_tenant_product(999999999, sample_tenant.id) is None
    assert len(ProductService.search_active_products("Test", sample_tenant.id)) >= 1
    assert isinstance(ProductService.search_active_products("Test", None), list)
    assert ProductService.find_customer_in_tenant(sample_customer.id, sample_tenant.id).id == sample_customer.id
    assert ProductService.find_customer_in_tenant(999999999, sample_tenant.id) is None
    assert ProductService.find_duplicate_product(sample_product.sku, "no-barcode", sample_tenant.id) is not None
    assert ProductService.find_duplicate_product("no-sku", "no-barcode", sample_tenant.id) is None
    assert ProductService.find_duplicate_product(sample_product.sku, "no-barcode", None) is not None


def test_counts_and_warehouse(db_session, sample_tenant, sample_product, sample_warehouse):
    from services.product_service import ProductService

    sales_n, purch_n = ProductService.transaction_counts(sample_product.id, sample_tenant.id)
    assert (sales_n, purch_n) == (0, 0)
    sales_n2, _ = ProductService.transaction_counts(sample_product.id, None)
    assert sales_n2 == 0
    assert ProductService.get_default_warehouse(sample_tenant.id) is not None
    sample_warehouse.is_main = True
    db_session.flush()
    assert ProductService.get_default_warehouse(sample_tenant.id) is not None
    sample_warehouse.is_main = False
    db_session.flush()
    assert ProductService.get_default_warehouse(sample_tenant.id) is not None


def test_category_product_count(db_session, sample_tenant, sample_product):
    from services.product_service import ProductService

    cat = ProductService.create_category("Count5", tenant_id=sample_tenant.id)
    db_session.flush()
    sample_product.category_id = cat.id
    db_session.flush()
    assert ProductService.count_products_in_category(sample_tenant.id, cat.id) == 1


def test_annotate_branches(mocker):
    from services import product_service as ps

    assert ps.ProductService.annotate_branch_and_warehouse_info([], [1]) == []
    prods = [SimpleNamespace(id=10)]
    out = ps.ProductService.annotate_branch_and_warehouse_info(prods, [])
    assert out[0].visible_warehouse_names == []

    sess = MagicMock()
    sess.session.query.return_value.join.return_value.outerjoin.return_value.filter.return_value.filter.return_value.all.return_value = [
        (10, "WH", None, "BR", "B1"),
        (10, None, None, None, None),
    ]
    mocker.patch.object(ps, "db", sess)
    out = ps.ProductService.annotate_branch_and_warehouse_info([SimpleNamespace(id=10)], [5])
    assert out[0].visible_warehouse_names == ["WH"]
    assert out[0].visible_branch_names == ["BR (B1)"]


def test_tenant_business_type(db_session, sample_tenant):
    from services.product_service import ProductService

    assert ProductService.tenant_business_type(999999999) is None
    sample_tenant.business_type = "Retail"
    db_session.flush()
    assert ProductService.tenant_business_type(sample_tenant.id) == "retail"


def test_scoped_customer_queries(db_session, sample_tenant, sample_customer, sample_branch):
    from services.product_service import ProductService

    assert isinstance(ProductService.scoped_customers_query("retail"), object)
    assert isinstance(ProductService.scoped_customers_query(None, branch_scope_id=sample_branch.id), object)
    assert isinstance(ProductService.scoped_customers("retail"), list)
    assert ProductService.find_scoped_customer(999999999, "retail") is None
