import os
import sys
sys.path.insert(0, 'D:\\Data\\karaj\\UAE\\Azad-UAE')

def test_shop_wishlist_model_exists():
    from models.shop_wishlist import ShopWishlist
    assert hasattr(ShopWishlist, '__tablename__')

def test_shop_review_model_exists():
    from models.shop_review import ShopReview
    assert hasattr(ShopReview, '__tablename__')

def test_wishlist_routes_exist():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'wishlist_add' in content, 'wishlist_add route missing'
    assert 'wishlist_remove' in content, 'wishlist_remove route missing'
    assert 'wishlist_view' in content, 'wishlist_view route missing'

def test_review_routes_exist():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\routes\\shop.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'add_review' in content, 'add_review route missing'
    assert 'product_reviews' in content, 'product_reviews route missing'

def test_wishlist_template_exists():
    path = 'D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\wishlist.html'
    assert os.path.exists(path), 'wishlist.html not found'

def test_wishlist_in_base_nav():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\base.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'wishlist' in content.lower() or 'heart' in content.lower()

def test_reviews_in_product():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\templates\\shop\\product.html', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'review' in content.lower() or 'rating' in content.lower()

def test_wishlist_js_handler():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\static\\js\\shop-cart.js', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'wishlist' in content.lower() or 'toggle' in content.lower() or 'wishlist' in content.lower()

def test_i18n_keys():
    from utils.shop_i18n import STRINGS
    keys = STRINGS.keys()
    for k in ['wishlist', 'wishlist_empty', 'reviews', 'write_review', 'rating', 'comment', 'submit_review', 'review_submitted']:
        assert k in keys, f'i18n key {k} missing'

def test_models_import_wishlist():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\models\\__init__.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'ShopWishlist' in content or 'shop_wishlist' in content

def test_models_import_review():
    with open('D:\\Data\\karaj\\UAE\\Azad-UAE\\models\\__init__.py', 'r', encoding='utf-8') as f:
        content = f.read()
    assert 'ShopReview' in content or 'shop_review' in content
