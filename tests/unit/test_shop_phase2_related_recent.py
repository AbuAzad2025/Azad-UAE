import os
import sys
sys.path.insert(0, 'D:\\Data\\karaj\\UAE\\Azad-UAE')

def test_get_related_products_exists():
    from services.store_service import StoreService
    assert hasattr(StoreService, 'get_related_products'), 'get_related_products missing'

def test_get_recently_viewed_exists():
    from services.store_service import StoreService
    assert hasattr(StoreService, 'get_recently_viewed_products'), 'get_recently_viewed_products missing'

def test_product_has_related_section():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\product.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'you_may_also_like' in content or 'related_products' in content or 'ps-related' in content

def test_product_has_recently_viewed():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\product.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'recently_viewed' in content or 'ps-recently' in content

def test_shop_recent_key_in_routes():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'shop_recent_' in content, 'Recently viewed session key not found in routes'

def test_related_products_context():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'related_products' in content, 'related_products not passed to template context'

def test_i18n_has_you_may_also_like():
    from utils.shop_i18n import STRINGS
    assert 'you_may_also_like' in STRINGS
    assert 'recently_viewed' in STRINGS
