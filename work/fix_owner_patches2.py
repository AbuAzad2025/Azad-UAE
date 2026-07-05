"""Add explicit sub-module level patches for render_template.

The propagation code approach was too fragile. Instead, add explicit
patch calls for each sub-module's render_template reference.
"""
import re

path = r'D:\Data\karaj\UAE\Azad-UAE\tests\unit\routes\test_owner_routes.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the propagation code with a simpler direct patch approach
old_propagation = """        # ── Propagate patched routes.owner attributes to sub-modules ──────
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
        # ── End propagation ───────────────────────────────────────────────"""

new_simple = """        # ── Patch sub-module render_template references ─────────────────
        # Sub-modules (core.py, etc.) do `from routes.owner import render_template`
        # at module load time. Patching routes.owner.render_template doesn't
        # affect those local references. Explicit patches are needed.
        _rt_patches = [
            (\"routes.owner.core.render_template\",
             patch(\"routes.owner.core.render_template\", return_value=\"ok\")),
            (\"routes.owner.tenants.render_template\",
             patch(\"routes.owner.tenants.render_template\", return_value=\"ok\")),
            (\"routes.owner.users.render_template\",
             patch(\"routes.owner.users.render_template\", return_value=\"ok\")),
            (\"routes.owner.backups.render_template\",
             patch(\"routes.owner.backups.render_template\", return_value=\"ok\")),
            (\"routes.owner.database.render_template\",
             patch(\"routes.owner.database.render_template\", return_value=\"ok\")),
            (\"routes.owner.settings.render_template\",
             patch(\"routes.owner.settings.render_template\", return_value=\"ok\")),
            (\"routes.owner.monitoring.render_template\",
             patch(\"routes.owner.monitoring.render_template\", return_value=\"ok\")),
            (\"routes.owner.shared.render_template\",
             patch(\"routes.owner.shared.render_template\", return_value=\"ok\")),
        ]
        for _, p in _rt_patches:
            stack.enter_context(p)
        # ── End sub-module patches ────────────────────────────────────────"""

if old_propagation in content:
    content = content.replace(old_propagation, new_simple)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ Simplified patch fix applied")
else:
    print("❌ Could not find propagation code")
    # See if the simpler fix from fix_owner_fixture.py was applied
    idx = content.find("owner_client(app_factory, bypass_owner_auth)")
    print(repr(content[idx:idx+250]))
    idx2 = content.find("_owner_patched_names")
    if idx2 >= 0:
        print("Found propagation at", idx2)
        print(repr(content[idx2:idx2+200]))
