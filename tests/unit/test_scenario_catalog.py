"""The gate that makes "no duplication" and "no omission" enforceable.

A catalogue is a document; this is the check. Three claims are verified here:

1. **No duplication** - a scenario identifier is claimed by exactly one test.
   Duplicated coverage is worse than none: it inflates the count while testing
   the same thing twice.
2. **No omission** - every blueprint in routes/ belongs to a catalogued domain,
   and every identifier uses a prefix the catalogue knows.
3. **Honest progress** - implemented scenarios are counted per domain against the
   budget the catalogue derives from the route inventory, so "62% done" cannot be
   claimed while the uncovered domains are the ones nobody tested.

The scenario identifier of a test is read from the ``@scenario`` marker, and for
the wave 0-6 files out of the ``S-NN`` in the docstring, which is where they
already live.
"""

from __future__ import annotations

import ast
import collections
import pathlib
import re

from tests.integration.business_scenarios import scenario_catalog as catalog

SCENARIO_DIR = pathlib.Path(__file__).resolve().parent.parent / "integration" / "business_scenarios"

#: ``@scenario("POS-07", "a held drawer must not close negative")``
_MARKER_NAME = "scenario"
#: ``"""S-07: the same operation, two roles, different outcomes."""``
_DOC_ID_RE = re.compile(r"\bS-(\d{2})\b")


def _id_of(func: ast.FunctionDef) -> str | None:
    """The scenario identifier a single test function claims.

    The marker wins over the docstring. Both are read from the *function*, never
    from the file as text: an earlier version scanned whole files with a regex and
    reported S-01 as duplicated because the identifier appears in the class
    docstring as well as the method's own - a bug in the gate, which is worse than
    no gate, because it cries wolf about real duplication.
    """
    for deco in func.decorator_list:
        target = deco.func if isinstance(deco, ast.Call) else deco
        name = getattr(target, "id", None) or getattr(target, "attr", None)
        if name == _MARKER_NAME:
            if isinstance(deco, ast.Call) and deco.args:
                first = deco.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    return first.value
    doc = ast.get_docstring(func) or ""
    found = _DOC_ID_RE.search(doc)
    return f"S-{found.group(1)}" if found else None


def _declared_ids() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Map every scenario identifier to the tests claiming it.

    A scenario is a business situation, and one situation is often asserted by
    several methods - the class docstring declares ``S-01`` and each method pins
    one facet of it. So an identifier legitimately has several methods behind it,
    and the duplication check is per *class*: two different classes claiming the
    same identifier is the real duplicate, because that is two suites asserting
    the same business rule independently.

    Resolution order is marker, then the method's own docstring, then the
    enclosing class's. Reading the whole file as text - the earlier version -
    reported S-01 as duplicated because the identifier appears in both docstrings,
    and found nothing at all once the reading moved to method level while the
    identifiers still lived at class level.
    """
    owners: dict[str, list[str]] = collections.defaultdict(list)
    hosts: dict[str, list[str]] = collections.defaultdict(list)
    for path in sorted(SCENARIO_DIR.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_id = _id_in_doc(node) or _id_in_markers(node)
                for fn in node.body:
                    if isinstance(fn, ast.FunctionDef) and fn.name.startswith("test_"):
                        sid = _id_of(fn) or class_id
                        if sid:
                            owners[sid].append(f"{path.name}::{node.name}::{fn.name}")
                            hosts[sid].append(f"{path.name}::{node.name}")
            elif isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                sid = _id_of(node)
                if sid:
                    owners[sid].append(f"{path.name}::{node.name}")
                    hosts[sid].append(path.name)
    return dict(owners), dict(hosts)


def _id_in_doc(node) -> str | None:
    found = _DOC_ID_RE.search(ast.get_docstring(node) or "")
    return f"S-{found.group(1)}" if found else None


def _id_in_markers(node) -> str | None:
    for deco in node.decorator_list:
        target = deco.func if isinstance(deco, ast.Call) else deco
        name = getattr(target, "id", None) or getattr(target, "attr", None)
        if name == _MARKER_NAME and isinstance(deco, ast.Call) and deco.args:
            first = deco.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                return first.value
    return None


class TestCatalogueIntegrity:
    def test_prefixes_are_unique(self):
        dupes = [p for p, n in collections.Counter(d.prefix for d in catalog.ALL_DOMAINS).items() if n > 1]
        assert not dupes, f"a domain prefix is used twice, so identifiers can collide: {dupes}"

    def test_no_blueprint_is_left_out(self):
        """A routes/ blueprint with no catalogued domain is an untested system."""
        live: dict[str, int] = {}
        for path in sorted((pathlib.Path.cwd() / "routes").rglob("*.py")):
            n = len(re.findall(r"@\w+\.route\(", path.read_text(encoding="utf-8", errors="replace")))
            if n:
                live[path.stem] = n
        covered = {b for d in catalog.ALL_DOMAINS for b in d.blueprints}
        missing = {k: v for k, v in live.items() if k not in covered}
        assert not missing, f"blueprints with no catalogued domain: {missing}"
        ghost = covered - set(live)
        assert not ghost, f"catalog names blueprints that do not exist: {sorted(ghost)}"

    def test_plan_reaches_the_target(self):
        assert catalog.coverage_gap() <= 0, (
            f"the catalogue only commits to {catalog.allocated_scenarios()} scenarios, "
            f"{catalog.coverage_gap()} short of {catalog.TARGET_SCENARIO_COUNT}"
        )

    def test_route_inventory_matches_the_tree(self):
        """The budgets are derived from measured route counts; if those drift, so must this."""
        live: dict[str, int] = {}
        for path in sorted((pathlib.Path.cwd() / "routes").rglob("*.py")):
            n = len(re.findall(r"@\w+\.route\(", path.read_text(encoding="utf-8", errors="replace")))
            if n:
                live[path.stem] = n
        stale = {k: (v, catalog._ROUTE_COUNTS.get(k)) for k, v in live.items() if catalog._ROUTE_COUNTS.get(k) != v}
        assert not stale, f"routes/ changed but the catalogue inventory did not: {stale}"


class TestScenarioIdentifiers:
    def test_no_scenario_is_claimed_by_two_suites(self):
        """The anti-duplication rule this whole catalogue exists for."""
        _, hosts = _declared_ids()
        dupes = {sid: sorted(set(h)) for sid, h in hosts.items() if len(set(h)) > 1}
        assert not dupes, f"these scenario identifiers are asserted by two different classes: {dupes}"

    def test_identifiers_use_a_catalogued_prefix(self):
        owners, _ = _declared_ids()
        known = catalog.PREFIXES | {f"S-{i:02d}" for i in range(1, 31)}
        unknown = sorted(sid for sid in owners if not any(sid == k or sid.startswith(k + "-") for k in known))
        assert not unknown, f"scenario identifiers outside the catalogue: {unknown}"

    def test_original_wave_scenarios_are_all_present(self):
        """S-01..S-30 must each still be claimed by exactly one suite."""
        _, hosts = _declared_ids()
        missing = [f"S-{i:02d}" for i in range(1, 31) if len(set(hosts.get(f"S-{i:02d}", []))) != 1]
        assert not missing, f"wave 0-6 scenarios claimed zero or several times: {missing}"


class TestProgressIsHonest:
    """Reporting, not gating.

    This prints the honest position so a claim of "62% done" can be checked
    against which domains are actually covered. It asserts nothing about the
    totals: a wave legitimately starts at zero, and a test that fails merely
    because work is outstanding is a test that trains people to ignore it.
    """

    def test_progress_report(self):
        owners, _ = _declared_ids()
        budgets = catalog.domain_budgets()
        implemented: collections.Counter = collections.Counter()
        for sid in owners:
            prefix = sid.split("-")[0]
            if prefix in budgets:
                implemented[prefix] += 1
        lines = [
            f"  {p:5} {implemented.get(p, 0):4}/{budgets[p]:<4}"
            f" {next(d.title for d in catalog.ALL_DOMAINS if d.prefix == p)[:52]}"
            for p in sorted(budgets)
        ]
        total_impl = len(owners)
        print(f"\nscenario budget: {sum(budgets.values())}   implemented: {total_impl}\n" + "\n".join(lines))
        assert lines, "the progress report rendered nothing"
