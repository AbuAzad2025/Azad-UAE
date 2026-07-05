"""Fix the owner_client fixture to import owner_bp inside the patches context.

The sub-modules (core.py, etc.) do `from routes.owner import render_template`
at module load time. The patches are applied AFTER the import, so local
references in sub-modules still point to the original functions.

Fix: move `from routes.owner import owner_bp` inside the `with _owner_route_patches():` block.
"""
import re

path = r'D:\Data\karaj\UAE\Azad-UAE\tests\unit\routes\test_owner_routes.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the owner_client fixture
old = """@pytest.fixture
def owner_client(app_factory, bypass_owner_auth):
    from routes.owner import owner_bp

    app = app_factory(owner_bp, {"SQLALCHEMY_DATABASE_URI": "postgresql://user:pass@localhost/testdb"})
    with _owner_route_patches():
        yield app.test_client()"""

new = """@pytest.fixture
def owner_client(app_factory, bypass_owner_auth):
    with _owner_route_patches():
        from routes.owner import owner_bp

        app = app_factory(owner_bp, {"SQLALCHEMY_DATABASE_URI": "postgresql://user:pass@localhost/testdb"})
        yield app.test_client()"""

if old in content:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ Fix applied successfully")
else:
    print("❌ Could not find the exact string to replace")
    # Try to find what's there
    idx = content.find("def owner_client")
    if idx >= 0:
        print("Found at position", idx)
        print(repr(content[idx:idx+350]))
