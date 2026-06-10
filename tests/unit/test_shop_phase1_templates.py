import os

def test_no_inline_style_in_shop_templates():
    templates = ['cart.html', 'checkout.html', 'product.html', 'order_success.html', 'base.html']
    base = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop'
    for name in templates:
        path = os.path.join(base, name)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        if 'ic-' in content and '<style>' in content:
            assert name == 'base.html', f'{name} still has <style> with ic- class'
        if name != 'base.html':
            assert '<style>' not in content, f'{name} still has <style> tag'

def test_shop_utilities_css_exists():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\static\\css\\shop-utilities.css'
    assert os.path.exists(path), 'shop-utilities.css not found'

def test_breadcrumbs_partial_exists():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\partials\\breadcrumbs.html'
    assert os.path.exists(path), 'breadcrumbs partial not found'

def test_product_json_ld():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\product.html'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'application/ld+json' in content, 'JSON-LD schema not found in product.html'
    assert '"@type": "Product"' in content, 'Product schema type not found'

def test_product_og_tags():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\product.html'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'og:title' in content, 'og:title not found'
    assert 'og:image' in content, 'og:image not found'
    assert 'twitter:card' in content, 'twitter:card not found'
    assert 'twitter:image' in content, 'twitter:image not found'

def test_breadcrumbs_in_templates():
    templates = ['catalog.html', 'cart.html', 'checkout.html', 'order_success.html', 'product.html']
    base = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop'
    for name in templates:
        path = os.path.join(base, name)
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'breadcrumbs.html' in content, f'{name} missing breadcrumbs include'

def test_base_html_keeps_variables():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    assert ':root' in content, 'base.html lost :root CSS variables'
    assert '--theme-primary' in content, 'base.html lost theme-primary variable'
