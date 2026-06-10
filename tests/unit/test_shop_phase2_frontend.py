import os

def test_shop_gallery_js_exists():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\static\\js\\shop-gallery.js'
    assert os.path.exists(path), 'shop-gallery.js not found'

def test_shop_quickview_js_exists():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\static\\js\\shop-quickview.js'
    assert os.path.exists(path), 'shop-quickview.js not found'

def test_quick_view_partial_exists():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\partials\\quick_view_modal.html'
    assert os.path.exists(path), 'quick_view_modal.html not found'

def test_quick_view_body_exists():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\partials\\quick_view_body.html'
    assert os.path.exists(path), 'quick_view_body.html not found'

def test_quick_view_route():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'quick_view' in content, 'quick_view route missing'

def test_quick_view_in_catalog():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\catalog.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'quick_view' in content or 'ps-quick-view' in content or 'data-quick-view' in content

def test_infinite_sentinel():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\catalog.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'ps-infinite-sentinel' in content, 'infinite scroll sentinel missing'

def test_gallery_in_product():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\product.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'ps-gallery-main' in content or 'data-zoom' in content, 'gallery structure missing'

def test_base_has_gallery_js():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'shop-gallery.js' in content, 'shop-gallery.js not loaded'

def test_base_has_quickview_js():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'shop-quickview.js' in content, 'shop-quickview.js not loaded'
