"""Fix: patch routes.owner.settings.db instead of routes.owner.db
in test_api_supervisor_override_success and _bad_password.
These routes are in settings.py which has a local db reference."""

test_file = "tests/unit/routes/test_owner_routes.py"

with open(test_file, "r", encoding="utf-8") as f:
    content = f.read()

fixes = [
    ('patch("routes.owner.db")', 'patch("routes.owner.settings.db")'),
]

changes = 0
for old, new in fixes:
    # Only fix the ones inside supervisor_override test methods
    # We need to find the right context - these tests are inside TestOwnerExtendedCoverage
    
    # Find all occurrences and fix them in context of supervisor_override tests
    # Actually let's just replace all inline patches that are in supervisor methods
    pass

# More targeted approach: find the specific methods
import re

# Replace in test_api_supervisor_override_success
idx1 = content.find("def test_api_supervisor_override_success")
if idx1 >= 0:
    # Find the with patch line within this method
    method_end = content.find("\n    def ", idx1 + 5)
    if method_end < 0:
        method_end = content.find("\nclass ", idx1 + 5)
    method_body = content[idx1:method_end]
    
    # Replace the patch("routes.owner.db") within this method body
    old_body = method_body
    new_body = method_body.replace('patch("routes.owner.db")', 'patch("routes.owner.settings.db")', 1)
    if new_body != old_body:
        content = content[:idx1] + new_body + content[idx1 + len(old_body):]
        changes += 1
        print(f"✅ Fixed test_api_supervisor_override_success")

# Replace in test_api_supervisor_override_bad_password
idx2 = content.find("def test_api_supervisor_override_bad_password")
if idx2 >= 0:
    method_end = content.find("\n    def ", idx2 + 5)
    if method_end < 0:
        method_end = content.find("\nclass ", idx2 + 5)
    method_body = content[idx2:method_end]
    old_body = method_body
    new_body = method_body.replace('patch("routes.owner.db")', 'patch("routes.owner.settings.db")', 1)
    if new_body != old_body:
        content = content[:idx2] + new_body + content[idx2 + len(old_body):]
        changes += 1
        print(f"✅ Fixed test_api_supervisor_override_bad_password")

if changes:
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\nTotal: {changes} fixes applied")
else:
    print("No changes made")
