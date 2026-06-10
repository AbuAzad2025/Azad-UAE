import os
import sys
sys.path.insert(0, 'D:\\Data\\karaj\\UAE\\Azad-UAE')

def test_search_api_endpoint():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'api/search' in content, 'Search API endpoint missing'

def test_get_public_catalog_has_sort():
    from services.store_service import StoreService
    import inspect
    sig = inspect.signature(StoreService.get_public_catalog)
    assert 'sort' in sig.parameters, 'sort param missing'

def test_get_public_catalog_has_filters():
    from services.store_service import StoreService
    import inspect
    sig = inspect.signature(StoreService.get_public_catalog)
    assert 'min_price' in sig.parameters, 'min_price param missing'
    assert 'max_price' in sig.parameters, 'max_price param missing'

def test_shop_search_js_exists():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\static\\js\\shop-search.js'
    assert os.path.exists(path), 'shop-search.js not found'

def test_catalog_has_sort():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\catalog.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'sort' in content or 'price_asc' in content, 'Sort dropdown missing'

def test_catalog_has_filters():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\catalog.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'min_price' in content or 'max_price' in content or 'in_stock_only' in content, 'Filters missing'

def test_base_html_has_search_js():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'shop-search.js' in content, 'shop-search.js not loaded in base.html'

def test_shop_i18n_has_sort_keys():
    from utils.shop_i18n import STRINGS
    keys = STRINGS.keys()
    assert 'sort_by' in keys
    assert 'price_low' in keys
    assert 'price_high' in keys
    assert 'in_stock_only' in keys
