"""Replace render_template-only patches with comprehensive attribute propagation.

All patched routes.owner.* attributes (render_template, db, User, Customer,
etc.) need to be propagated to sub-module namespaces because sub-modules
import locally at module load time.
"""
import re

path = r'D:\Data\karaj\UAE\Azad-UAE\tests\unit\routes\test_owner_routes.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the render_template-only patches with comprehensive propagation
old = """        # ── Patch sub-module render_template references ─────────────────
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

new = """        # ── Propagate ALL patched routes.owner attributes to sub-modules ──
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

if old in content:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ Comprehensive propagation fix applied")
else:
    print("❌ Could not find the render_template-only patches")
    idx = content.find("Propagate ALL")
    if idx >= 0:
        print("Already fixed!")
    else:
        idx2 = content.find("Patch sub-module render_template")
        if idx2 >= 0:
            print("Found at", idx2)
            print(repr(content[idx2:idx2+100]))
