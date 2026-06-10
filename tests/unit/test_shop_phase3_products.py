import os
import sys
sys.path.insert(0, 'D:\\Data\\karaj\\UAE\\Azad-UAE')

def test_variant_model():
    from models.shop_product_variant import ShopProductVariant
    assert hasattr(ShopProductVariant, '__tablename__')
    assert ShopProductVariant.__tablename__ == 'shop_product_variants'

def test_stock_alert_model():
    from models.shop_stock_alert import ShopStockAlert
    assert hasattr(ShopStockAlert, '__tablename__')

def test_loyalty_model():
    from models.shop_loyalty import ShopLoyalty
    assert hasattr(ShopLoyalty, '__tablename__')

def test_variant_route():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'variants' in content or 'get_product_variants' in content

def test_stock_alert_route():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'stock_alert' in content

def test_variant_selector_in_product():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\product.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'variant' in content.lower() or 'ps-variant' in content

def test_stock_alert_in_product():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\product.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'stock_alert' in content or 'stock-alert' in content or 'notify_me' in content

def test_loyalty_in_checkout():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\checkout.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'loyalty' in content.lower() or 'loyalty_points' in content

def test_models_init_imports():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\models\\__init__.py', 'r', encoding='utf-8') as f:
        content = f.read()
    for name in ['ShopProductVariant', 'ShopStockAlert', 'ShopLoyalty', 'ShopLoyaltyTransaction']:
        assert name in content, f'{name} not imported in __init__.py'

def test_get_product_variants_exists():
    from services.store_service import StoreService
    assert hasattr(StoreService, 'get_product_variants'), 'get_product_variants missing'
