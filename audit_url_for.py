"""
Comprehensive url_for <-> endpoint audit for Azadexa.
"""

import os, re, json, sys
from collections import defaultdict

OUT = open("url_audit_report.txt", "w", encoding="utf-8")

def log(*args):
    text = " ".join(str(a) for a in args)
    print(text, file=OUT)
    print(text)

# ── 1. Scan source files for url_for ────────────────────────────────────

def scan_url_for(root_dir, extensions):
    pattern = re.compile(r"url_for\([\"\']([^\"\']+)[\"\'][^)]*\)")
    results = defaultdict(list)
    for root, dirs, files in os.walk(root_dir):
        for f in files:
            if f.endswith(extensions):
                path = os.path.join(root, f)
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        content = fh.read()
                    for m in pattern.finditer(content):
                        endpoint = m.group(1)
                        if " " in endpoint or endpoint.startswith("."):
                            continue
                        line_no = content[:m.start()].count("\n") + 1
                        results[endpoint].append(f"{path}:{line_no}")
                except Exception:
                    pass
    return dict(results)


def extract_endpoints():
    from app import create_app
    app = create_app()
    with app.app_context():
        return {r.endpoint for r in app.url_map.iter_rules()}


def group_by_blueprint(endpoints):
    groups = defaultdict(list)
    for ep in endpoints:
        bp = ep.split(".")[0] if "." in ep else "_global"
        groups[bp].append(ep)
    return {k: sorted(v) for k, v in groups.items()}


def main():
    log("=" * 70)
    log("AZADEXA URL_FOR / ENDPOINT COMPREHENSIVE AUDIT")
    log("=" * 70)

    # ── Extract url_for references ──
    log("")
    log("[1/4] Scanning url_for references in source code...")
    url_for_refs = scan_url_for("templates", (".html", ".jinja", ".j2"))
    for subdir in ("routes", "services", "utils", "models"):
        if os.path.isdir(subdir):
            extra = scan_url_for(subdir, (".py",))
            for k, v in extra.items():
                url_for_refs.setdefault(k, []).extend(v)
    for extra_file in ("extensions.py", "app.py"):
        if os.path.isfile(extra_file):
            extra = scan_url_for(".", (extra_file,))
            for k, v in extra.items():
                url_for_refs.setdefault(k, []).extend(v)
    url_for_refs = {k: sorted(set(v)) for k, v in url_for_refs.items()}
    log(f"  Found {len(url_for_refs)} distinct url_for endpoints referenced.")

    # ── Extract Flask endpoints ──
    log("")
    log("[2/4] Loading Flask application and extracting registered endpoints...")
    endpoints = extract_endpoints()
    log(f"  Found {len(endpoints)} registered Flask endpoints.")

    # ── Cross-analysis ──
    log("")
    log("[3/4] Performing cross-match analysis...")

    broken = {ep: locs for ep, locs in url_for_refs.items() if ep not in endpoints}
    referenced = set(url_for_refs.keys())
    orphaned = endpoints - referenced - {"static"}

    ep_by_bp = group_by_blueprint(endpoints)
    ref_by_bp = group_by_blueprint(referenced)

    # ── Build report ──
    log("")
    log("[4/4] Generating report...")
    log("")
    log("=" * 70)
    log("REPORT: BROKEN url_for (non-existent endpoints)")
    log("=" * 70)
    if broken:
        log(f"")
        log(f"Count: {len(broken)}")
        log(f"")
        for ep, locs in sorted(broken.items()):
            log(f"  X {ep}")
            for loc in locs:
                log(f"      -> {loc}")
    else:
        log("")
        log("  OK - NONE FOUND -- all url_for references point to valid endpoints.")
        log("")

    log("")
    log("=" * 70)
    log("REPORT: ORPHANED ENDPOINTS (no url_for reference)")
    log("=" * 70)
    orphan_by_bp = group_by_blueprint(orphaned)
    if orphaned:
        log(f"")
        log(f"Count: {len(orphaned)}")
        log(f"")
        for bp in sorted(orphan_by_bp.keys(), key=lambda b: -len(orphan_by_bp[b])):
            eps = orphan_by_bp[bp]
            log(f"  {bp}: {len(eps)} endpoint(s)")
            for ep in sorted(eps)[:15]:
                log(f"      . {ep}")
            if len(eps) > 15:
                log(f"      ... and {len(eps)-15} more")
    else:
        log("")
        log("  OK - NONE FOUND -- every endpoint is referenced somewhere.")
        log("")

    log("")
    log("=" * 70)
    log("REPORT: BLUEPRINT-LEVEL COVERAGE")
    log("=" * 70)
    all_bps = sorted(set(ep_by_bp.keys()) | set(ref_by_bp.keys()))
    for bp in all_bps:
        ep_count = len(ep_by_bp.get(bp, []))
        ref_count = len(ref_by_bp.get(bp, []))
        orphan_count = len([e for e in ep_by_bp.get(bp, []) if e in orphaned])
        coverage = (ref_count / ep_count * 100) if ep_count else 0
        status = "OK" if orphan_count == 0 else f"WARN {orphan_count} orphaned"
        log(f"  {bp:20s}  endpoints={ep_count:3d}  referenced={ref_count:3d}  coverage={coverage:5.1f}%  {status}")

    log("")
    log("=" * 70)
    log("REPORT: TOP REFERENCED ENDPOINTS")
    log("=" * 70)
    top = sorted(url_for_refs.items(), key=lambda kv: -len(kv[1]))[:20]
    for ep, locs in top:
        log(f"  {ep:50s}  referenced in {len(locs)} location(s)")

    log("")
    log("=" * 70)
    log("STATISTICAL SUMMARY")
    log("=" * 70)
    log(f"  Total registered endpoints:          {len(endpoints)}")
    log(f"  Distinct url_for references:         {len(url_for_refs)}")
    log(f"  Broken url_for (non-existent):       {len(broken)}")
    log(f"  Orphaned endpoints (unreferenced):   {len(orphaned)}")
    referenced_count = len(referenced)
    coverage_pct = (referenced_count / len(endpoints) * 100) if endpoints else 0
    log(f"  Overall coverage:                    {referenced_count}/{len(endpoints)} ({coverage_pct:.1f}%)")
    log("=" * 70)

    report = {
        "meta": {
            "total_endpoints": len(endpoints),
            "total_url_for_refs": len(url_for_refs),
            "broken_count": len(broken),
            "orphaned_count": len(orphaned),
            "coverage_pct": round(coverage_pct, 2),
        },
        "broken": {k: v for k, v in sorted(broken.items())},
        "orphaned": sorted(orphaned),
        "orphaned_by_blueprint": {k: sorted(v) for k, v in sorted(orphan_by_bp.items())},
        "blueprint_summary": [
            {
                "blueprint": bp,
                "endpoints": len(ep_by_bp.get(bp, [])),
                "referenced": len(ref_by_bp.get(bp, [])),
                "orphaned": len([e for e in ep_by_bp.get(bp, []) if e in orphaned]),
            }
            for bp in all_bps
        ],
    }
    with open("url_audit_report.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    log("")
    log("Full JSON report saved to: url_audit_report.json")
    OUT.close()


if __name__ == "__main__":
    main()
