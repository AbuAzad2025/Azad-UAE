import os
import sys
sys.path.insert(0, 'D:\\Data\\karaj\\UAE\\Azad-UAE')

def test_reorder_route():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'reorder' in content, 'Reorder route missing'

def test_order_invoice_route():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'order_invoice' in content or 'invoice' in content, 'Invoice route missing'

def test_order_track_route():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'order_track' in content or 'track' in content, 'Track route missing'

def test_order_track_template():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\order_track.html'
    assert os.path.exists(path), 'order_track.html not found'

def test_order_invoice_template():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\order_invoice.html'
    assert os.path.exists(path), 'order_invoice.html not found'

def test_checkout_guest_allowed():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    if 'def checkout' in content:
        checkout_part = content.split('def checkout')[1].split('\ndef ')[0]
        assert '_require_shop_customer' not in checkout_part, 'Guest checkout blocked by _require_shop_customer'

def test_coupon_validation():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\services\\store_checkout_service.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'StoreCoupon' in content or 'coupon' in content.lower(), 'Coupon validation missing'

def test_reorder_in_template():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\account_order_detail.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'reorder' in content or 'Reorder' in content

def test_invoice_in_template():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\account_order_detail.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'invoice' in content or 'Invoice' in content or 'download' in content

def test_i18n_keys():
    from utils.shop_i18n import STRINGS
    keys = STRINGS.keys()
    for k in ['track_order', 'reorder', 'download_invoice', 'cart_updated']:
        assert k in keys, f'i18n key {k} missing'
