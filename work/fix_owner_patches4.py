"""Fix by adding explicit sub-module render_template patches via stack.enter_context.

The propagation approach doesn't work because of scope issues. Instead, use
explicit stack.enter_context() calls with patch() for each sub-module.
"""
import re

path = r'D:\Data\karaj\UAE\Azad-UAE\tests\unit\routes\test_owner_routes.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the propagation code and replace with explicit patch calls
old = """        # ── Propagate ALL patched routes.owner attributes to sub-modules ──
        # Sub-modules do `from routes.owner import X` at module load time,
        # creating local references. Patching routes.owner.X doesn't affect
        # those local references. Here we overwrite them with patched values.
        import routes.owner as _own_mod
        _owner_attrs = {
            name.split(\".\")[-1]
            for name_str, _ in patches
            if name_str.startswith(\"routes.owner.\") and name_str.count(\".\") == 2
        }
        for _sub_name in (\"core\", \"tenants\", \"users\", \"backups\", \"database\", \"settings\", \"monitoring\", \"shared\"):
            _sub = getattr(_own_mod, _sub_name, None)
            if _sub is None:
                continue
            _sub_dict = vars(_sub)
            for _attr in _owner_attrs:
                if _attr in _sub_dict:
                    setattr(_sub, _attr, getattr(_own_mod, _attr))
        # ── End propagation ───────────────────────────────────────────────"""

new = """        # ── Explicit sub-module patches for render_template ──────────────
        # Sub-modules do `from routes.owner import render_template` at module
        # load time. Patching routes.owner.render_template does NOT affect
        # the already-imported local references in sub-modules.
        for _sub_mod in (\"core\", \"tenants\", \"users\", \"backups\", \"database\", \"settings\", \"monitoring\", \"shared\"):
            stack.enter_context(
                patch(f\"routes.owner.{_sub_mod}.render_template\", return_value=\"ok\")
            )
        # ── End sub-module patches ────────────────────────────────────────"""

if old in content:
    # Check if this is the ONLY occurrence
    count = content.count(old)
    if count == 1:
        content = content.replace(old, new)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("✅ Explicit patch fix applied")
    else:
        print(f"❌ Found {count} occurrences, expected 1")
else:
    print("❌ Could not find propagation code")
    # Try to find what's there
    idx = content.find("Propagate ALL")
    if idx >= 0:
        print("Found 'Propagate ALL' at", idx)
        print(repr(content[idx:idx+150]))
