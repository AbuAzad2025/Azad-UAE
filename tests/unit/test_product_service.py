def test_product_service_exists():
    from services.product_service import product_get_cost, product_get_stock
    assert callable(product_get_cost)
    assert callable(product_get_stock)
