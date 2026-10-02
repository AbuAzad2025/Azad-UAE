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
import sys

REPORT_DIR = pathlib.Path(".lighthouseci")
CONFIG = pathlib.Path("scripts/lighthouserc.json")

# Checked only so a page that renders but is not actually usable (an error page
# still gets a score) cannot be reported as healthy.
SANITY_FLOOR = 0.5


def _gate_thresholds() -> dict[str, float]:
    """Read minScore per category from the lhci assert config.

    Only the flat `assertions` map is read. An `assert.matrix` form was tried
    here and in lighthouserc.json and `lhci assert` rejected it outright with
    "No assertions to use", so there is no per-URL gate to mirror.

    That single SEO floor is why it is 0.65: / scores 100 and /auth/login scores
    69, the latter being deliberately noindex. A 0.90 floor blocks forever on a
    page that is correct; 0.65 still catches a real SEO break, which lands well
    under half. Getting a tight SEO budget onto / alone needs two lhci configs
    and two collect passes, not a matrix.
    """
    try:
        raw = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        assertions = raw["ci"]["assert"]["assertions"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"FAIL: cannot read {CONFIG}: {exc}", file=sys.stderr)
        return {}

    floors: dict[str, float] = {}
    for key, spec in assertions.items():
        if not key.startswith("categories:"):
            continue
        if isinstance(spec, list) and len(spec) == 2 and isinstance(spec[1], dict):
            floors[key.split(":", 1)[1]] = float(spec[1].get("minScore", SANITY_FLOOR))
    return floors


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
    thresholds = _gate_thresholds()
    if not thresholds:
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
