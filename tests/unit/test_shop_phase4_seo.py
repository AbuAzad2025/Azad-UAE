import os
import sys
sys.path.insert(0, 'D:\\Data\\karaj\\UAE\\Azad-UAE')

def test_robots_txt_route():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'robots.txt' in content

def test_cookie_banner():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'cookie' in content.lower()

def test_newsletter_model():
    from models.shop_newsletter import ShopNewsletter
    assert hasattr(ShopNewsletter, '__tablename__')

def test_newsletter_route():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'newsletter_subscribe' in content

def test_newsletter_in_footer():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'newsletter' in content.lower()

def test_social_sharing():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\product.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'facebook.com/sharer' in content or 'share' in content.lower()

def test_utm_tracking():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'utm_' in content

def test_noindex_meta():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'noindex' in content

def test_noindex_on_cart():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'noindex=True' in content

def test_ga_tracking():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'gtag' in content or 'analytics' in content.lower()

def test_i18n_keys():
    from utils.shop_i18n import STRINGS
    for k in ['cookie_notice', 'cookie_accept', 'newsletter', 'subscribe', 'share']:
        assert k in STRINGS.keys(), f'i18n key {k} missing'
