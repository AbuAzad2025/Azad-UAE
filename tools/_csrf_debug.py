from dotenv import load_dotenv
load_dotenv(".env")
import re
from app import create_app
from models.shop_customer_account import ShopCustomerAccount
from services.shop_customer_auth_service import ShopCustomerAuthService

app = create_app()
app.config["WTF_CSRF_SSL_STRICT"] = False
with app.app_context():
    acct = ShopCustomerAccount.query.filter_by(tenant_id=2).first()
    with app.test_client() as c:
        with c.session_transaction() as s:
            s[ShopCustomerAuthService.session_key(2)] = acct.id
        r = c.get("/s/test-a")
        tok = re.findall(r'name="csrf_token"\s+value="([^"]+)"', r.data.decode())[0]
        r2 = c.post(
            "/s/test-a/cart/add",
            data={"product_id": 36, "quantity": 1, "csrf_token": tok},
            headers={"X-CSRFToken": tok, "Referer": "http://localhost/s/test-a"},
        )
        print("post", r2.status_code)
        with c.session_transaction() as s:
            print("cart", s.get("shop_cart_2"))
