import os
import sys
sys.path.insert(0, 'D:\\Data\\karaj\\UAE\\Azad-UAE')

def test_abandoned_cart_model():
    from models.shop_abandoned_cart import ShopAbandonedCart
    assert hasattr(ShopAbandonedCart, '__tablename__')

def test_saved_payment_model():
    from models.shop_saved_payment import ShopSavedPayment
    assert hasattr(ShopSavedPayment, '__tablename__')

def test_abandoned_cart_tracking():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert '_track_cart_activity' in content

def test_saved_payment_routes():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'saved_payments' in content
    assert 'save_payment' in content
    assert 'delete_saved_payment' in content

def test_saved_payments_template():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\saved_payments.html'
    assert os.path.exists(path)

def test_celery_abandoned_task():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\services\\celery_tasks.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'send_abandoned_cart_reminders' in content

def test_abandoned_cart_beat_schedule():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\services\\celery_tasks.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'abandoned' in content.lower()

def test_models_init_imports():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\models\\__init__.py', 'r', encoding='utf-8') as f:
        content = f.read()
    for name in ['ShopAbandonedCart', 'ShopSavedPayment']:
        assert name in content

def test_i18n_keys():
    from utils.shop_i18n import STRINGS
    for k in ['saved_payments', 'payment_saved', 'payment_deleted']:
        assert k in STRINGS.keys()

def test_saved_payments_in_base_nav():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'saved_payments' in content
