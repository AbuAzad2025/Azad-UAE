"""Replace render_template-only sub-module patches with comprehensive propagation of ALL patched routes.owner attributes to sub-modules.

This combines the best of both approaches: uses explicit setattr (like the propagation code) but also verifies it works by using hasattr check.
"""
import re

path = r'D:\Data\karaj\UAE\Azad-UAE\tests\unit\routes\test_owner_routes.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the render_template-only patches with comprehensive propagation
old = """        # ── Explicit sub-module patches for render_template ──────────────
        # Sub-modules do `from routes.owner import render_template` at module
        # load time. Patching routes.owner.render_template does NOT affect
        # the already-imported local references in sub-modules.
        for _sub_mod in (\"core\", \"tenants\", \"users\", \"backups\", \"database\", \"settings\", \"monitoring\", \"shared\"):
            stack.enter_context(
                patch(f\"routes.owner.{_sub_mod}.render_template\", return_value=\"ok\")
            )
        # ── End sub-module patches ────────────────────────────────────────"""

new = """        # ── Propagate ALL patched routes.owner attributes to sub-modules ──
        # Sub-modules do `from routes.owner import X` at module load time,
        # creating local references. Patching routes.owner.X doesn't affect
        # those local references. Explicitly overwrite them.
        import routes.owner as _own_mod
        _owner_names = {
            name_str.split(\".\", 2)[2]
            for name_str, _ in patches
            if name_str.startswith(\"routes.owner.\") and name_str.count(\".\") == 2
        }
        for _sn in (\"core\", \"tenants\", \"users\", \"backups\", \"database\", \"settings\", \"monitoring\", \"shared\"):
            _sm = getattr(_own_mod, _sn, None)
            if _sm is None:
                continue
            _sd = vars(_sm)
            for _an in _owner_names:
                if _an in _sd:
                    setattr(_sm, _an, getattr(_own_mod, _an))
        # ── End propagation ───────────────────────────────────────────────"""

if old in content:
    count = content.count(old)
    if count == 1:
        content = content.replace(old, new)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ Comprehensive propagation fix applied")
    else:
        print(f"❌ Found {count} occurrences, expected 1")
else:
    print("❌ Could not find the explicit render_template-only patches text")
    idx = content.find("Propagate ALL")
    if idx >= 0:
        print("Already has 'Propagate ALL' text!")

# Also verify the fix_owner_fixture change is in place
if "    with _owner_route_patches():" in content and "        from routes.owner import owner_bp" in content:
    print("✅ Owner fixture import reorder is in place")
else:
    print("❌ Owner fixture import reorder NOT found")
