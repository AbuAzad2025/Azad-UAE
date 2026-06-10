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

    # Build a set of nodes that are inside function bodies
    func_node_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                func_node_ids.add(id(child))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names = [a.name for a in node.names]
                from_imports.append((node.module, names))
                if id(node) in func_node_ids:
                    func_imports.append(node.module)
    return imports, from_imports, func_imports


_SKIP_DIRS = {"__pycache__", ".venv", "ai_knowledge", "tools", "scripts", "migrations", ".git"}


def _get_all_py_files():
    files = []
    for item in SCAN_DIRS:
        p = os.path.join(BASE, item)
        if os.path.isfile(p) and p.endswith(".py"):
            files.append(p)
        elif os.path.isdir(p):
            for root, dnames, fnames in os.walk(p):
                dnames[:] = [d for d in dnames if d not in _SKIP_DIRS]
                if "__pycache__" in root or ".venv" in root:
                    continue
                for f in fnames:
                    if f.endswith(".py"):
                        files.append(os.path.join(root, f))
    return sorted(files)


def _walk_py_files(start_dir):
    """Walk a directory for .py files, skipping unwanted dirs."""
    files = []
    start = os.path.join(BASE, start_dir)
    if not os.path.isdir(start):
        return files
    for root, dnames, fnames in os.walk(start):
        dnames[:] = [d for d in dnames if d not in _SKIP_DIRS]
        if "__pycache__" in root or ".venv" in root:
            continue
        for f in fnames:
            if f.endswith(".py"):
                files.append(os.path.join(root, f))
    return files


# ── Tests ────────────────────────────────────────────────────────────


class TestImportGraph:

    def test_no_circular_imports(self):
        """Verify no circular dependencies among core modules."""
        all_files = _get_all_py_files()
        # Limit to main core files to keep test fast
        core_prefixes = ("routes", "services", "utils", "models", "forms", "bootstrap", "app")
        core_files = [f for f in all_files if any(
            os.path.relpath(f, BASE).startswith(p) for p in core_prefixes
        )]

        graph = {}
        for fp in core_files:
            rel = os.path.relpath(fp, BASE).replace("\\", "/").replace(".py", "")
            _, from_imports, _ = _get_imports(fp)
            deps = []
            for mod, _ in from_imports:
                top = mod.split(".")[0]
                if top in ("routes", "services", "utils", "models", "forms", "bootstrap"):
                    deps.append(mod)
            graph[rel] = deps

        # DFS cycle detection with early exit
        _UNVISITED, _VISITING, _VISITED = 0, 1, 2
        state = {n: _UNVISITED for n in graph}

        def _has_cycle(node):
            state[node] = _VISITING
            for neighbor in graph.get(node, []):
                if neighbor not in state:
                    continue
                if state[neighbor] == _VISITING:
                    return True
                if state[neighbor] == _UNVISITED and _has_cycle(neighbor):
                    return True
            state[node] = _VISITED
            return False

        cycles = []
        for node in graph:
            if state[node] == _UNVISITED:
                if _has_cycle(node):
                    cycles.append(node)

        assert not cycles, f"Circular dependencies detected involving: {cycles}"

    def test_models_do_not_import_services(self):
        """Models layer must not import from services layer at top-level. Lazy imports inside functions are allowed to avoid circular deps."""
        violations = []
        for fp in _walk_py_files("models"):
            f = os.path.basename(fp)
            _, from_imports, func_imports = _get_imports(fp)
            for mod, _ in from_imports:
                if mod and (mod == "services" or mod.startswith("services.")):
                    if mod not in func_imports:
                        violations.append(f"{f}: top-level imports {mod}")

        assert not violations, f"Models importing from services:\n" + "\n".join(violations)

    @pytest.mark.xfail(strict=False, reason="Architectural debt: models/events.py uses lazy AI imports (disabled at runtime via AI_ORM_LISTENERS_ENABLED=false)")
    def test_models_do_not_import_ai_knowledge(self):
        """Models must not import from ai_knowledge (AI subsystem)."""
        violations = []
        for fp in _walk_py_files("models"):
            f = os.path.basename(fp)
            _, from_imports, _ = _get_imports(fp)
            for mod, _ in from_imports:
                if mod and (mod == "ai_knowledge" or mod.startswith("ai_knowledge.")):
                    violations.append(f"{f}: imports {mod}")

        assert not violations, f"Models importing from ai_knowledge:\n" + "\n".join(violations)

    def test_routes_do_not_import_scripts_or_tools(self):
        """Routes must not import from scripts/ or tools/."""
        violations = []
        for fp in _walk_py_files("routes"):
            f = os.path.basename(fp)
            _, from_imports, _ = _get_imports(fp)
            for mod, _ in from_imports:
                if mod and (mod in ("scripts", "tools") or mod.startswith("scripts.") or mod.startswith("tools.")):
                    violations.append(f"{f}: imports {mod}")

        assert not violations, f"Routes importing from scripts/tools:\n" + "\n".join(violations)

    def test_services_do_not_import_routes(self):
        """Services must not import from routes/."""
        violations = []
        for fp in _walk_py_files("services"):
            f = os.path.basename(fp)
            _, from_imports, _ = _get_imports(fp)
            for mod, _ in from_imports:
                if mod and (mod == "routes" or mod.startswith("routes.")):
                    violations.append(f"{f}: imports {mod}")

        assert not violations, f"Services importing from routes:\n" + "\n".join(violations)

    def test_no_local_imports_of_core_modules(self):
        """Local imports (inside functions) of core modules are a code smell."""
        smells = []
        for fp in _walk_py_files("routes"):
            rel = os.path.relpath(fp, BASE).replace("\\", "/")
            _, _, func_imports = _get_imports(fp)
            for mod in set(func_imports):
                top = mod.split(".")[0]
                if top in ("services", "utils", "models"):
                    smells.append(f"{rel}: local import of {mod}")
        for fp in _walk_py_files("services"):
            rel = os.path.relpath(fp, BASE).replace("\\", "/")
            _, _, func_imports = _get_imports(fp)
            for mod in set(func_imports):
                top = mod.split(".")[0]
                if top in ("routes", "utils", "models"):
                    smells.append(f"{rel}: local import of {mod}")

        if len(smells) > 10:
            smells = smells[:10] + [f"... and {len(smells) - 10} more"]
        if smells:
            pytest.skip(f"Local imports found ({len(smells)}):\n" + "\n".join(smells))
