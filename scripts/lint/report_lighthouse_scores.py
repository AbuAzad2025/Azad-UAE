"""Print the real Lighthouse scores and fail loudly when nothing was measured.

LHCI's log only shows scores when an assertion trips, so a green job tells you
nothing about how green it is. This reads the JSON lhci wrote and states the
numbers, using the thresholds from scripts/lighthouserc.json rather than a
second copy: if the gate's floors move, this report moves with them instead of
quietly approving a score the gate would reject.

THE RULE
--------

Every audited URL is measured N times, where N is ``collect.numberOfRuns`` in
scripts/lighthouserc.json (currently 3). The gate is decided on the **median
run** of those N - the run whose performance score is the median of the runs -
and every category of that run has to clear its floor. Each category's median
across the runs has to clear its floor too.

Why the median run and not one arbitrary run: a CI runner measures a page
whose *server* was cold for the first request, and that cold request is a
property of the runner, not of the page. The same commit scored 65 on one run
and 97 on the next, from the same code, on the same URL. One sample cannot
tell a regression from a cold start. Three samples can, and the median of them
removes the single-sample artefact *without* moving a floor: a page that is
genuinely slow is slow in its median as well, and the spread is printed so a
page whose measurement is unstable is visible rather than hidden.

The representative runs are written to .lighthouse-gate/.lighthouseci/ so that
``lhci assert``, run from that directory, checks exactly the numbers printed
here instead of every individual run (which would fail the build on the one
cold run this rule exists to ignore).

Exits non-zero when no report was produced. A missing report is not a pass - it
means lhci never measured the URLs, and reporting success there would recreate
the silent failure this gate exists to prevent.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import statistics
import sys

REPORT_DIR = pathlib.Path(".lighthouseci")
CONFIG = pathlib.Path("scripts/lighthouserc.json")
# The directory `lhci assert` is run from. It holds the representative run per
# URL, named the way lhci expects (lhr-<digits>.json).
GATE_DIR = pathlib.Path(".lighthouse-gate")

# Checked only so a page that renders but is not actually usable (an error page
# still gets a score) cannot be reported as healthy.
SANITY_FLOOR = 0.5


def _load_config() -> dict:
    """Read the lhci config, or an empty dict if it cannot be read."""
    try:
        raw = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


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
    assertions = _load_config().get("ci", {}).get("assert", {}).get("assertions", {})
    if not isinstance(assertions, dict):
        print(f"FAIL: cannot read the assert block in {CONFIG}", file=sys.stderr)
        return {}

    floors: dict[str, float] = {}
    for key, spec in assertions.items():
        if not key.startswith("categories:"):
            continue
        if isinstance(spec, list) and len(spec) == 2 and isinstance(spec[1], dict):
            floors[key.split(":", 1)[1]] = float(spec[1].get("minScore", SANITY_FLOOR))
    return floors


def _expected_runs() -> int:
    """How many runs per URL the collect step is configured to produce.

    Read from the same config the floors come from, so the rule this script
    prints ("median of N") and the number of runs lhci actually performs cannot
    drift apart.
    """
    number = _load_config().get("ci", {}).get("collect", {}).get("numberOfRuns", 1)
    try:
        return max(1, int(number))
    except (TypeError, ValueError):
        return 1


def _scores(report: dict) -> dict[str, float]:
    """Category scores of one Lighthouse run."""
    out: dict[str, float] = {}
    for name, cat in (report.get("categories") or {}).items():
        value = cat.get("score") if isinstance(cat, dict) else None
        if value is not None:
            out[name] = float(value)
    return out


def _url_of(report: dict) -> str:
    return report.get("finalDisplayedUrl") or report.get("requestedUrl") or "?"


def _run_key(report: dict) -> str:
    """Identify the *run* a report belongs to.

    lhci writes every run twice: once as `lhr-<timestamp>.json` from collect
    and once as `<host>-<path>-<date>.report.json` from the filesystem upload.
    Both copies carry the same `fetchTime`, so it identifies the run. A report
    without one falls back to a hash of its content.
    """
    fetch_time = report.get("fetchTime")
    if fetch_time:
        return f"t:{fetch_time}"
    blob = json.dumps(report, sort_keys=True, default=str).encode("utf-8")
    return f"h:{hashlib.sha256(blob).hexdigest()}"


def _group_runs(reports: list[dict]) -> tuple[dict[str, list[dict]], list[str]]:
    """Group the reports into one entry per run, per URL.

    The copies of a single run collapse. Copies of the *same* run that
    disagree are a different thing: one of them is corrupt, and silently
    picking either one is how a regression gets approved by a lucky copy, so
    the conflict is returned as a failure.
    """
    by_run: dict[tuple[str, str], dict] = {}
    conflicts: list[str] = []
    for report in reports:
        url = _url_of(report)
        key = (url, _run_key(report))
        existing = by_run.get(key)
        if existing is None:
            by_run[key] = report
            continue
        if _scores(existing) != _scores(report):
            rendered = " vs ".join(
                " ".join(f"{k}={v:.2f}" for k, v in sorted(_scores(r).items())) for r in (existing, report)
            )
            conflicts.append(f"{url}: two copies of the same run disagree - {rendered}")

    grouped: dict[str, list[dict]] = {}
    for (url, _key), report in by_run.items():
        grouped.setdefault(url, []).append(report)
    for runs in grouped.values():
        runs.sort(key=lambda r: (r.get("fetchTime") or "", _run_key(r)))
    return grouped, conflicts


def _median_run(runs: list[dict]) -> dict:
    """The run whose performance score is the median of the runs.

    Performance is the category that has been observed to swing between runs
    (65 on one run, 97 on the next, same commit), so it is the one the
    representative run is selected on.

    Only runs that produced a performance score are eligible. A run without
    one is a measurement that did not happen - Lighthouse reports the error in
    the audit (NO_LCP on the login page, seen in a local run) and leaves the
    category score null - and such a run must never be picked as the
    representative one.
    """
    eligible = [r for r in runs if _scores(r).get("performance") is not None]
    if not eligible:
        return {}

    def perf(report: dict) -> float:
        return _scores(report)["performance"]

    median = statistics.median([perf(r) for r in eligible])
    return min(eligible, key=lambda r: (abs(perf(r) - median), r.get("fetchTime") or ""))


def _unusable(runs: list[dict], category: str) -> list[str]:
    """Runs that produced no score for a category, with Lighthouse's reason.

    A null score is not a page that scored badly, it is a measurement that
    did not happen. It is reported by name so the log says which run was
    dropped and why, instead of the run silently disappearing from the median.
    """
    problems: list[str] = []
    for run in runs:
        if _scores(run).get(category) is not None:
            continue
        reason = ""
        audit = (run.get("audits") or {}).get("largest-contentful-paint")
        if category == "performance" and isinstance(audit, dict):
            reason = f" ({audit.get('errorMessage')})" if audit.get("errorMessage") else ""
        problems.append(f"{run.get('fetchTime') or 'unknown timestamp'}{reason}")
    return problems


def _write_gate_reports(representatives: dict[str, dict]) -> list[str]:
    """Write the representative run of each URL for `lhci assert` to check.

    lhci assert reads `lhr-<digits>.json` from the .lighthouseci directory of
    the current working directory, so the files are written into
    .lighthouse-gate/.lighthouseci/ and the assert step runs from
    .lighthouse-gate. The raw runs stay untouched in .lighthouseci/ as the
    evidence.
    """
    problems: list[str] = []
    gate = GATE_DIR / ".lighthouseci"
    try:
        if gate.exists():
            for stale in gate.glob("lhr-*.json"):
                stale.unlink()
        gate.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return [f"cannot prepare {gate}: {exc}"]

    for index, (_url, report) in enumerate(sorted(representatives.items()), start=1):
        if not report:
            # No usable run for this URL - the report already failed. Writing
            # an empty file would only give `lhci assert` something to choke
            # on, and it would not run anyway.
            continue
        try:
            (gate / f"lhr-{index}.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        except OSError as exc:
            problems.append(f"cannot write the representative report: {exc}")
    return problems


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

    expected_runs = _expected_runs()
    reports, broken = _load_reports()
    if not reports:
        print(f"FAIL: no usable Lighthouse report in {REPORT_DIR}/ - nothing was measured.")
        print("      This step only reads what lhci wrote; the measurement was lost EARLIER,")
        print("      in this job's own log. Read these steps, in this order:")
        print("        1. 'Start app server'                     - did the server ever answer 200?")
        print("        2. 'Warm up and verify the audited pages' - did every audited URL settle on 200?")
        print("        3. 'Run Lighthouse CI'                    - did `lhci collect` / `lhci upload` run?")
        print("      The first one that FAILED is the cause; this step is only where the absence became visible.")
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

    grouped, conflicts = _group_runs(reports)
    failures.extend(conflicts)

    print(
        f"Gate rule: median of {expected_runs} run(s) per URL. The gate is decided on the "
        "median run\n(the run whose performance score is the median); every category of that "
        "run and every\ncategory's median across the runs must clear its floor."
    )
    print(f"Floors from {CONFIG}: " + ", ".join(f"{k} {v * 100:.0f}" for k, v in sorted(thresholds.items())))
    print()

    representatives: dict[str, dict] = {}
    for url, runs in sorted(grouped.items()):
        if len(runs) < expected_runs:
            # Not a failure on its own: the collect step exits non-zero when it
            # cannot produce its runs, so this only fires if the config and the
            # collection disagree. It is loud because the rule printed above
            # claims a median of N and this is not N.
            print(
                f"  WARNING: {url} - {len(runs)} run(s) collected, {expected_runs} expected; "
                "the median is taken over what was measured."
            )
        representative = _median_run(runs)
        representatives[url] = representative

        print(f"  {url}")
        unusable = _unusable(runs, "performance")
        for item in unusable:
            print(f"    WARNING: run {item} produced no performance score - excluded from the median")
        if not representative:
            failures.append(f"{url}: no run produced a performance score - nothing to gate")
            print("    MISSING performance      no run produced a score")
            print()
            continue
        for name in sorted(thresholds):
            measured = [_scores(run).get(name) for run in runs]
            values: list[float] = [v for v in measured if v is not None]
            if not values:
                print(f"    MISSING {name:<16}   --")
                continue
            median = statistics.median(values)
            spread = max(values) - min(values)
            rendered = " / ".join(f"{v * 100:.1f}" for v in values)
            print(
                f"    runs  {name:<16} {rendered}   median {median * 100:5.1f}  "
                f"min {min(values) * 100:5.1f}  max {max(values) * 100:5.1f}  spread {spread * 100:4.1f}"
            )
            if spread > 0.05:
                print(f"          ^ unstable measurement: the runs differ by {spread * 100:.1f} points")
            if median < thresholds[name]:
                failures.append(
                    f"{url}: {name} median of {len(values)} run(s) scored {median * 100:.1f} < gate {thresholds[name] * 100:.0f}"
                )
        print(f"    median run: {representative.get('fetchTime') or 'unknown'}")
        for name, floor in sorted(thresholds.items()):
            category = (representative.get("categories") or {}).get(name)
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

        runtime = representative.get("runtimeError") or {}
        # Lighthouse omits runtimeError entirely when the page loaded; a falsy
        # code also means no error, so only a real code is a failure.
        if runtime.get("code"):
            failures.append(f"{url}: runtime error {runtime.get('code')}")
        print()

    failures.extend(_write_gate_reports(representatives))

    if failures:
        print("\nFAIL:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print(f"All measured pages rendered and cleared the gate (median of {expected_runs} run(s)).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
