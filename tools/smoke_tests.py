import os
import sys


def _status_ok(code: int) -> bool:
    return code in (200, 302, 303)


def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("DEBUG", "1")
    os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")

    from app import create_app
    from extensions import db
    from models import Branch, Customer, Product, Sale, Supplier, User

    app = create_app()
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        branch = Branch.query.order_by(Branch.is_main.desc(), Branch.id.asc()).first()
        assert branch is not None

        seller = User.query.filter(User.username.like("seller_%")).order_by(User.id.asc()).first()
        assert seller is not None

        counts = {
            "branches": Branch.query.count(),
            "users": User.query.count(),
            "products": Product.query.count(),
            "customers": Customer.query.count(),
            "suppliers": Supplier.query.count(),
            "sales": Sale.query.count(),
        }
        for k, v in counts.items():
            if v <= 0:
                raise AssertionError(f"count_{k}=0")

        client = app.test_client()

        r = client.get("/auth/login")
        assert _status_ok(r.status_code)

        login_form = {
            "username": seller.username,
            "password": "123456",
            "branch_id": str(branch.id),
        }
        r = client.post("/auth/login", data=login_form, follow_redirects=False)
        assert r.status_code in (302, 303)

        r = client.get("/dashboard")
        assert _status_ok(r.status_code)

        for path in ("/products/", "/customers/", "/sales/", "/purchases/", "/expenses/"):
            r = client.get(path)
            if not _status_ok(r.status_code) and r.status_code != 403:
                raise AssertionError(f"{path} status={r.status_code}")

        db.session.execute(db.text("SELECT 1"))

        print("SMOKE_OK")
        for k, v in counts.items():
            print(f"{k.upper()}={v}")
        print(f"LOGIN_USER={seller.username}")
        print(f"LOGIN_BRANCH_ID={branch.id}")


if __name__ == "__main__":
    main()
