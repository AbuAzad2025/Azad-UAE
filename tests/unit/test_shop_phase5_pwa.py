import os
import sys
sys.path.insert(0, 'D:\\Data\\karaj\\UAE\\Azad-UAE')

def test_manifest_exists():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\static\\shop-manifest.json'
    assert os.path.exists(path)

def test_manifest_link_in_base():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'manifest' in content

def test_service_worker_exists():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\static\\sw.js'
    assert os.path.exists(path)

def test_service_worker_registered():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'serviceWorker' in content

def test_offline_template():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\offline.html'
    assert os.path.exists(path)

def test_offline_route():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'offline' in content

def test_font_preload():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'preload' in content and 'font' in content.lower()

def test_install_banner():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'install' in content.lower() or 'ps-install-banner' in content

def test_theme_color():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'theme-color' in content

def test_i18n_keys():
    from utils.shop_i18n import STRINGS
    for k in ['install_app', 'install', 'offline', 'offline_title', 'offline_msg', 'try_again']:
        assert k in STRINGS.keys(), f'i18n key {k} missing'
