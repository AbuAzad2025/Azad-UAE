"""Print the real Lighthouse scores and fail loudly when nothing was measured.

LHCI's log only shows scores when an assertion trips, so a green job tells you
nothing about how green it is. This reads the JSON lhci wrote and states the
numbers, using the thresholds from scripts/lighthouserc.json rather than a
second copy: if the gate's floors move, this report moves with them instead of
quietly approving a score the gate would reject.

Exits non-zero when no report was produced. A missing report is not a pass - it
means lhci never measured the URLs, and reporting success there would recreate
the silent failure this gate exists to prevent.
"""

from __future__ import annotations

import json
import pathlib
import re

REPORT_DIR = pathlib.Path(".lighthouseci")
CONFIG = pathlib.Path("scripts/lighthouserc.json")

# Checked only so a page that renders but is not actually usable (an error page
# still gets a score) cannot be reported as healthy.
SANITY_FLOOR = 0.5


def _gate_thresholds() -> tuple[list[tuple[str, dict[str, float]]], str]:
    """Read minScore per category from the lhci assert config.

    Returns (per-url-pattern thresholds, default pattern). lhci supports either a
    flat `assertions` map or a `matrix` keyed by matchingUrlPattern; this reads
    both so the printed gates are always the enforced ones.
    """
    try:
        raw = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        assert_cfg = raw["ci"]["assert"]
    except (OSError, ValueError, KeyError, TypeError):
        return [], ".*"

    def parse(spec: object) -> dict[str, float]:
        floors: dict[str, float] = {}
        if not isinstance(spec, dict):
            return floors
        for key, rule in spec.items():
            if not key.startswith("categories:"):
                continue
            if isinstance(rule, list) and len(rule) == 2 and isinstance(rule[1], dict):
                floors[key.split(":", 1)[1]] = float(rule[1].get("minScore", SANITY_FLOOR))
        return floors

    matrix = assert_cfg.get("matrix")
    if isinstance(matrix, list) and matrix:
        entries: list[tuple[str, dict[str, float]]] = []
        default: dict[str, float] = {}
        for item in matrix:
            if not isinstance(item, dict):
                continue
            pattern = str(item.get("matchingUrlPattern", ".*"))
            floors = parse(item.get("assertions"))
            if pattern == ".*":
                default = floors
            else:
                entries.append((pattern, floors))
        if default:
            entries.append((".*", default))
        return entries, ".*"

    floors = parse(assert_cfg.get("assertions"))
    return ([(".*", floors)] if floors else []), ".*"


def _thresholds_for(url: str, entries: list[tuple[str, dict[str, float]]], default: str) -> dict[str, float]:
    """Most specific matching pattern wins; falls back to the default entry.

    lhci's matchingUrlPattern is a regular expression, not a glob - fnmatch is
    wrong twice over: it mis-globs, and on Windows normcase rewrites the "/" in a
    URL to "\" so no URL ever matches.
    """
    best: dict[str, float] = {}
    best_len = -1
    for pattern, floors in entries:
        try:
            hit = re.search(pattern, url) is not None
        except re.error:
            hit = False
        if hit and len(pattern) > best_len:
            best, best_len = floors, len(pattern)
    return best


def _dedupe(reports: list[dict]) -> tuple[list[dict], list[str]]:
    """One entry per URL, keeping the worst score seen.

    collect writes .lighthouseci/ and the filesystem upload copies into the same
    directory, so a page legitimately arrives more than once with identical
    numbers. Those collapse silently. Reports that *disagree* are a different
    thing: picking either one silently is how a regression gets approved by a
    lucky copy, so the conflict is returned as a failure and the lower score is
    used.
    """
    grouped: dict[str, list[dict]] = {}
    for report in reports:
        url = report.get("finalDisplayedUrl") or report.get("requestedUrl") or "?"
        grouped.setdefault(url, []).append(report)

    collapsed: list[dict] = []
    conflicts: list[str] = []
    for url, items in grouped.items():
        if len(items) == 1:
            collapsed.append(items[0])
            continue

        def scores(r: dict) -> dict[str, float]:
            out = {}
            for name, cat in (r.get("categories") or {}).items():
                value = cat.get("score") if isinstance(cat, dict) else None
                if value is not None:
                    out[name] = float(value)
            return out

        variants = {tuple(sorted(scores(r).items())) for r in items}
        if len(variants) > 1:
            rendered = " vs ".join(" ".join(f"{k}={v:.2f}" for k, v in sorted(scores(r).items())) for r in items)
            conflicts.append(f"{url}: reports disagree - {rendered}")
        collapsed.append(min(items, key=lambda r: min(scores(r).values(), default=1.0)))
    return collapsed, conflicts


def _load_reports() -> tuple[list[dict], list[str]]:
    if not REPORT_DIR.is_dir():
        return [], []
    reports: list[dict] = []
    broken: list[str] = []
    for path in sorted(REPORT_DIR.glob("*.json")):
        try:
            # utf-8-sig tolerates a BOM; lhci writes plain UTF-8.
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            broken.append(f"{path.name}: {exc}")
            continue
        # manifest.json is an index, not a report.
        if isinstance(data, dict) and "categories" in data:
            reports.append(data)
    return reports, broken


def main() -> int:
    entries, default = _gate_thresholds()
    if not entries:
        print(f"FAIL: no category thresholds found in {CONFIG} - the gate constrains nothing.")
        return 1

    reports, broken = _load_reports()
    if not reports:
        print(f"FAIL: no usable Lighthouse report in {REPORT_DIR}/ - nothing was measured.")
        if broken:
            # A report that exists but will not parse is a different fault from
            # no report at all; saying otherwise hides the real cause.
            print("      Reports were present but unreadable:")
            for item in broken:
                print(f"        - {item}")
        else:
            print("      A missing report is a failure, not a pass.")
        return 1

    failures = [f"unreadable report: {item}" for item in broken]

    unique, conflicts = _dedupe(reports)
    failures.extend(conflicts)
    for report in unique:
        url = report.get("finalDisplayedUrl") or report.get("requestedUrl") or "?"
        thresholds = _thresholds_for(url, entries, default)
        if not thresholds:
            failures.append(f"{url}: no gate matched this URL")
            print(f"  {url}\n    NO GATE MATCHED THIS URL")
            continue
        print(f"  {url}")
        for name, floor in thresholds.items():
            category = report.get("categories", {}).get(name)
            score = None if category is None else category.get("score")
            if score is None:
                failures.append(f"{url}: {name} has no score")
                print(f"    MISSING {name:<16}   --")
                continue
            pct = score * 100
            mark = "ok  " if score >= floor else "FAIL"
            print(f"    {mark} {name:<16} {pct:5.1f}  (gate {floor * 100:.0f})")
            if score < floor:
                failures.append(f"{url}: {name} scored {pct:.1f} < gate {floor * 100:.0f}")
            elif score < SANITY_FLOOR:
                failures.append(f"{url}: {name} scored {pct:.1f} - rendered but unusable")

        runtime = report.get("runtimeError") or {}
        # Lighthouse omits runtimeError entirely when the page loaded; a falsy
        # code also means no error, so only a real code is a failure.
        if runtime.get("code"):
            failures.append(f"{url}: runtime error {runtime.get('code')}")

    if failures:
        print("\nFAIL:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("\nAll measured pages rendered and cleared the gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
