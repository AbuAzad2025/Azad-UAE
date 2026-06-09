import os
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("WTF_CSRF_ENABLED", "false")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("CACHE_TYPE", "null")
os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")

from app import create_app
from tests.conftest import TestConfig
app = create_app(TestConfig)

with app.app_context():
    from extensions import db
    db.create_all()

client = app.test_client()
resp = client.get('/owner/dashboard')
print(f"Status (no session): {resp.status_code}")
print(f"Response length: {len(resp.data)}")
body = resp.data.decode('utf-8')
if 'dashboard' in body.lower() or 'لوحة' in body:
    print("Body contains dashboard text - it's rendering the dashboard!")
elif '404' in body:
    print("Body contains 404 text")
elif 'login' in body.lower() or 'تسجيل' in body:
    print("Body contains login text")
else:
    print(f"Body snippet: {body[:300]}")
