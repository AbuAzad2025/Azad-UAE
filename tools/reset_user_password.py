import os
import sys


def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    username = (os.environ.get("RESET_USERNAME") or "").strip()
    new_password = os.environ.get("RESET_PASSWORD") or ""
    if not username or not new_password:
        raise SystemExit("Set RESET_USERNAME and RESET_PASSWORD environment variables.")

    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("DEBUG", "1")
    os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")

    from app import create_app
    from extensions import db
    from models import User

    app = create_app()
    with app.app_context():
        user = User.query.filter(User.username.ilike(username)).first()
        if not user:
            raise SystemExit(f"User not found: {username}")
        user.set_password(new_password)
        db.session.commit()
        print("OK")


if __name__ == "__main__":
    main()

