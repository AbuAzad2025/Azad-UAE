"""Fix: patch routes.owner.database.db instead of routes.owner.db
in test_execute_query_db_error, because database.py has a local
db reference from 'from routes.owner import (... db ...)' that
isn't affected by patching routes.owner.db after fixture setup."""

test_file = "tests/unit/routes/test_owner_routes.py"

with open(test_file, "r", encoding="utf-8") as f:
    content = f.read()

old = '''    def test_execute_query_db_error(self, owner_client):
        with patch("routes.owner.db") as mock_db:'''

new = '''    def test_execute_query_db_error(self, owner_client):
        with patch("routes.owner.database.db") as mock_db:'''

if old in content:
    content = content.replace(old, new)
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(content)
    print("✅ Fixed: patched routes.owner.database.db instead of routes.owner.db")
else:
    print("⚠️  Pattern not found in file. Checking exact bytes...")
    # Find the test method
    idx = content.find("def test_execute_query_db_error")
    if idx != -1:
        print(f"Found at position {idx}")
        print(repr(content[idx:idx+120]))
    else:
        print("Method not found at all!")
