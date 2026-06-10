import os
import sys
sys.path.insert(0, 'D:\\Data\\karaj\\UAE\\Azad-UAE')


def test_get_public_catalog_returns_pagination():
    """Verify get_public_catalog returns pagination info."""
    from services.store_service import StoreService
    import inspect
    sig = inspect.signature(StoreService.get_public_catalog)
    params = sig.parameters
    assert 'page' in params, 'get_public_catalog missing page param'
    assert 'per_page' in params, 'get_public_catalog missing per_page param'
    assert params['page'].default == 1, 'page default should be 1'
    assert params['per_page'].default == 24, 'per_page default should be 24'


def test_pagination_partial_exists():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\partials\\pagination.html'
    assert os.path.exists(path)


def test_is_ajax_helper():
    """Verify _is_ajax function exists in routes/shop.py."""
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert '_is_ajax' in content, '_is_ajax helper not found'


def test_cart_count_route():
    """Verify cart_count route exists."""
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'cart/count' in content, 'cart/count route not found'


def test_cart_jsonify():
    """Verify jsonify is imported and used."""
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'jsonify' in content, 'jsonify not imported or used'


def test_guest_cart_allowed():
    """Verify cart routes no longer require login."""
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    cart_view_section = content.split('def cart_view(')[1].split('def ')[0] if 'def cart_view' in content else ''
    assert '_require_shop_customer' not in cart_view_section, 'cart_view still requires login'


def test_store_context_always_calculates_cart():
    """Verify _store_context calculates cart_count for all users."""
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    start = content.find('def _store_context')
    end = content.find('\n\n', content.find('return {', start))
    if end == -1:
        end = content.find('def ', content.find('return {', start))
    func = content[start:end]
    assert 'cart_count' in func
    assert 'if account else 0' not in func, '_store_context still has if account else 0'


def test_catalog_includes_pagination():
    """Verify catalog template includes pagination partial."""
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\catalog.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'pagination' in content or 'pagina' in content.lower(), 'catalog.html missing pagination'


def test_routes_import_jsonify():
    """Verify jsonify is available in routes/shop.py for AJAX responses."""
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'from flask import' in content
    assert 'jsonify' in content


def test_checkout_no_login_required():
    """Verify checkout route does not require login."""
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    checkout_section = content.split('def checkout(')[1].split('def ')[0] if 'def checkout' in content else ''
    assert '_require_shop_customer' not in checkout_section, 'checkout still requires login'


def test_catalog_has_page_param():
    """Verify catalog route passes page/pagination to template."""
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    catalog_section = content.split('def catalog(slug):')[1].split('def ')[0] if 'def catalog' in content else ''
    assert "catalog_result['page']" in catalog_section, 'catalog route missing page in render_template'
    assert "catalog_result['pages']" in catalog_section, 'catalog route missing pages in render_template'
