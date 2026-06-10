import os

def test_shop_cart_js_exists():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\static\\js\\shop-cart.js'
    assert os.path.exists(path), 'shop-cart.js not found'

def test_shop_cart_js_has_required_functions():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\static\\js\\shop-cart.js'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'addToCart' in content, 'addToCart function missing'
    assert 'removeFromCart' in content, 'removeFromCart function missing'
    assert 'updateCartBadge' in content, 'updateCartBadge function missing'
    assert 'showToast' in content, 'showToast function missing'
    assert 'apiPost' in content, 'apiPost function missing'

def test_shop_storefront_enhanced():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\static\\js\\shop-storefront.js'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'data-qty-minus' in content or 'qty' in content, 'qty buttons missing'
    assert 'navToggle' in content or 'nav-toggle' in content or 'ps-nav' in content, 'nav toggle missing'

def test_base_html_has_csrf_meta():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'csrf-token' in content, 'csrf meta tag not found'

def test_base_html_has_cart_js():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'shop-cart.js' in content, 'shop-cart.js not loaded in base.html'

def test_base_html_has_store_slug_data():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'data-store-slug' in content, 'data-store-slug not found on body'

def test_catalog_has_ajax_cart():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\catalog.html'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'data-ajax-cart' in content, 'catalog.html missing data-ajax-cart'

def test_cart_has_ajax_remove():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\cart.html'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'data-ajax-remove' in content, 'cart.html missing data-ajax-remove'
