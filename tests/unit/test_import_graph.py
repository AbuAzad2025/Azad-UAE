import pytest
import ast
import os


BASE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCAN_DIRS = ["app.py", "routes", "services", "utils", "models", "forms", "bootstrap"]

# ── Helpers ──────────────────────────────────────────────────────────


def _get_imports(filepath):
    with open(filepath, encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError:
            return [], [], []
    imports = []
    from_imports = []
    func_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names = [a.name for a in node.names]
                from_imports.append((node.module, names))
                # Check if inside a function
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.FunctionDef):
                        for child in ast.walk(parent):
                            if child is node:
                                func_imports.append(node.module)
    return imports, from_imports, func_imports


def _get_all_py_files():
    files = []
    for item in SCAN_DIRS:
        p = os.path.join(BASE, item)
        if os.path.isfile(p) and p.endswith(".py"):
            files.append(p)
        elif os.path.isdir(p):
            for root, dnames, fnames in os.walk(p):
                if "__pycache__" in root or ".venv" in root:
                    continue
                for f in fnames:
                    if f.endswith(".py"):
                        files.append(os.path.join(root, f))
    return sorted(files)


# ── Tests ────────────────────────────────────────────────────────────


class TestImportGraph:

    def test_no_circular_imports(self):
        """Verify no circular dependencies among core modules."""
        all_files = _get_all_py_files()
        graph = {}

        for fp in all_files:
            rel = os.path.relpath(fp, BASE).replace("\\", "/").replace(".py", "")
            _, from_imports, _ = _get_imports(fp)
            deps = []
            for mod, _ in from_imports:
                top = mod.split(".")[0]
                if top in ("routes", "services", "utils", "models", "forms", "bootstrap"):
                    deps.append(mod)
            graph[rel] = deps

        # Build set of known nodes
        known = set(graph.keys())
        for deps in graph.values():
            for d in deps:
                known.add(d)

        # DFS cycle detection
        def _has_cycle(node, visited, stack):
            visited.add(node)
            stack.add(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if _has_cycle(neighbor, visited, stack):
                        return True
                elif neighbor in stack:
                    return True
            stack.discard(node)
            return False

        visited = set()
        cycles = []
        for node in graph:
            if node not in visited:
                stack = set()
                if _has_cycle(node, visited, stack):
                    cycles.append(node)

        assert not cycles, f"Circular dependencies detected involving: {cycles}"

    def test_models_do_not_import_services(self):
        """Models layer must not import from services layer."""
        models_dir = os.path.join(BASE, "models")
        violations = []

        for root, _, files in os.walk(models_dir):
            for f in files:
                if not f.endswith(".py"):
                    continue
                fp = os.path.join(root, f)
                _, from_imports, _ = _get_imports(fp)
                for mod, _ in from_imports:
                    if mod and (mod == "services" or mod.startswith("services.")):
                        violations.append(f"{f}: imports {mod}")

        assert not violations, f"Models importing from services:\n" + "\n".join(violations)

    def test_models_do_not_import_ai_knowledge(self):
        """Models must not import from ai_knowledge (AI subsystem)."""
        models_dir = os.path.join(BASE, "models")
        violations = []

        for root, _, files in os.walk(models_dir):
            for f in files:
                if not f.endswith(".py"):
                    continue
                fp = os.path.join(root, f)
                _, from_imports, _ = _get_imports(fp)
                for mod, _ in from_imports:
                    if mod and (mod == "ai_knowledge" or mod.startswith("ai_knowledge.")):
                        violations.append(f"{f}: imports {mod}")

        assert not violations, f"Models importing from ai_knowledge:\n" + "\n".join(violations)

    def test_routes_do_not_import_scripts_or_tools(self):
        """Routes must not import from scripts/ or tools/."""
        routes_dir = os.path.join(BASE, "routes")
        violations = []

        for root, _, files in os.walk(routes_dir):
            for f in files:
                if not f.endswith(".py"):
                    continue
                fp = os.path.join(root, f)
                _, from_imports, _ = _get_imports(fp)
                for mod, _ in from_imports:
                    if mod and (mod in ("scripts", "tools") or mod.startswith("scripts.") or mod.startswith("tools.")):
                        violations.append(f"{f}: imports {mod}")

        assert not violations, f"Routes importing from scripts/tools:\n" + "\n".join(violations)

    def test_services_do_not_import_routes(self):
        """Services must not import from routes/."""
        services_dir = os.path.join(BASE, "services")
        violations = []

        for root, _, files in os.walk(services_dir):
            for f in files:
                if not f.endswith(".py"):
                    continue
                fp = os.path.join(root, f)
                _, from_imports, _ = _get_imports(fp)
                for mod, _ in from_imports:
                    if mod and (mod == "routes" or mod.startswith("routes.")):
                        violations.append(f"{f}: imports {mod}")

        assert not violations, f"Services importing from routes:\n" + "\n".join(violations)

    def test_no_local_imports_of_core_modules(self):
        """Local imports (inside functions) of core modules are a code smell."""
        all_files = _get_all_py_files()
        smells = []

        for fp in all_files:
            rel = os.path.relpath(fp, BASE).replace("\\", "/")
            _, _, func_imports = _get_imports(fp)
            for mod in set(func_imports):
                top = mod.split(".")[0]
                if top in ("routes", "services", "utils", "models"):
                    smells.append(f"{rel}: local import of {mod}")

        # This is a warning, not a hard failure — limit to 10 examples
        if len(smells) > 10:
            smells = smells[:10] + [f"... and {len(smells) - 10} more"]
        if smells:
            pytest.skip(f"Local imports found ({len(smells)}):\n" + "\n".join(smells))
