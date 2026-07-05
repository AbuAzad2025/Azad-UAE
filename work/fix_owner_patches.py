"""Add sub-module attribute propagation after patches are applied.

After all patches for routes.owner.X are entered, propagate the patched
values to sub-module namespaces (core, tenants, users, etc.) because
sub-modules import via `from routes.owner import X` at module load time,
creating local references.
"""
import re

path = r'D:\Data\karaj\UAE\Azad-UAE\tests\unit\routes\test_owner_routes.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the end of _owner_route_patches - look for 'yield' in the function
# The pattern is: after all patches, there's a 'yield' statement.
# We need to insert propagation code before the yield.

# Find the line after the last patch line and before yield
old = """        stack.enter_context(patch(\"models.ProductWarehouseCost\", _model_class()))
        yield"""

new = """        stack.enter_context(patch(\"models.ProductWarehouseCost\", _model_class()))
        # ── Propagate patched routes.owner attributes to sub-modules ──────
        # Sub-modules (core.py, tenants.py, etc.) do `from routes.owner import X`
        # at module load time, creating local references. Patching
        # routes.owner.X doesn't affect those local references.
        # Here we overwrite sub-module attributes with the patched values.
        _owner_patched_names = {
            name.split(\".\")[-1]
            for name_str, _ in patches
            if name_str.startswith(\"routes.owner.\") and name_str.count(\".\") == 2
        }
        import routes.owner as _own_mod
        for _sub_name in (\"core\", \"tenants\", \"users\", \"backups\", \"database\", \"settings\", \"monitoring\", \"shared\"):
            _sub = getattr(_own_mod, _sub_name, None)
            if _sub is None:
                continue
            for _attr in _owner_patched_names:
                if hasattr(_sub, _attr):
                    setattr(_sub, _attr, getattr(_own_mod, _attr))
        # ── End propagation ───────────────────────────────────────────────
        yield"""

if old in content:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ Patch propagation fix applied successfully")
else:
    print("❌ Could not find the exact string")
    # Debug: find what's there
    idx = content.find("ProductWarehouseCost")
    if idx >= 0:
        print(repr(content[idx:idx+150]))
