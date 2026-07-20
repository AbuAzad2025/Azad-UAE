#!/usr/bin/env python3
"""
Comprehensive coverage report for Azad-UAE CI.

Reads combined .coverage data and template tracking files to produce
a markdown summary with:
  - Backend (Python) coverage by category (routes, services, models, etc.)
  - Frontend (template) rendering coverage
  - JS file reachability via rendered templates

Usage: python scripts/coverage_report.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

BACKEND_CATEGORIES = [
    ("routes", "Routes (API/Web)"),
    ("services", "Services (Business Logic)"),
    ("models", "Models (Data Layer)"),
    ("utils", "Utils & ORM"),
    ("forms", "Forms & Validation"),
    ("app", "App & Factory"),
    ("bootstrap", "Bootstrap"),
    ("app.runtime", "Runtime Core"),
    ("ai_knowledge", "AI & Knowledge"),
]

_SCRIPT_RE = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
_INCLUDE_RE = re.compile(
    r'{%-?\s*(?:include|extends|from)\s+["\']([^"\']+)["\']', re.IGNORECASE
)


def _norm(p: str) -> str:
    return os.path.normpath(p).replace("\\", "/")


# ── Backend coverage ──────────────────────────────────────────────────────


def get_backend_coverage():
    """Return list of (key, label, files, total, covered, pct) tuples."""
    try:
        import coverage
    except ImportError:
        return None

    try:
        cov = coverage.Coverage()
        cov.load()
    except Exception:
        return None

    data = cov.get_data()
    measured_raw = data.measured_files()

    stats = defaultdict(lambda: {"total": 0, "covered": 0, "files": 0})

    measured_set = {_norm(p) for p in measured_raw}

    for cat, _ in BACKEND_CATEGORIES:
        cat_dir = PROJECT_ROOT / cat
        if not cat_dir.is_dir():
            continue
        for py_file in cat_dir.rglob("*.py"):
            norm = _norm(str(py_file.relative_to(PROJECT_ROOT)))
            try:
                _, stmts, _, missing, _ = cov.analysis2(str(py_file))
                total = len(stmts)
                covered = total - len(missing)
            except Exception:
                total = _count_statements(py_file)
                covered = 0
            stats[cat]["total"] += total
            stats[cat]["covered"] += covered
            stats[cat]["files"] += 1

    results = []
    a_total = a_cov = a_files = 0
    for cat, label in BACKEND_CATEGORIES:
        t = stats[cat]["total"]
        c = stats[cat]["covered"]
        f = stats[cat]["files"]
        pct = (c / t * 100) if t else 0
        results.append((cat, label, f, t, c, pct))
        a_total += t
        a_cov += c
        a_files += f

    a_pct = (a_cov / a_total * 100) if a_total else 0
    results.append(("_overall", "Backend Total", a_files, a_total, a_cov, a_pct))
    return results


def _count_statements(path: Path) -> int:
    """Count executable statements in a Python file (approximate)."""
    try:
        import ast

        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        return sum(1 for _ in ast.walk(tree) if isinstance(_, ast.stmt))
    except Exception:
        return 1


# ── Frontend template coverage ────────────────────────────────────────────


def _collect_rendered_templates() -> set[str]:
    rendered: set[str] = set()

    local = PROJECT_ROOT / "templates_rendered.json"
    if local.exists():
        try:
            with open(local, encoding="utf-8") as f:
                rendered.update(json.load(f))
        except Exception:
            pass

    artifacts_base = PROJECT_ROOT / "template-data"
    if artifacts_base.exists():
        for p in artifacts_base.rglob("templates_rendered.json"):
            try:
                with open(p, encoding="utf-8") as f:
                    rendered.update(json.load(f))
            except Exception:
                pass

    return rendered


def _expand_includes(rendered: set[str], all_templates: set[str]) -> set[str]:
    """Expand {% include %} / {% extends %} / {% from ... import %} in rendered templates."""
    templates_dir = PROJECT_ROOT / "templates"
    expanded = set(rendered)
    changed = True
    while changed:
        changed = False
        for name in list(expanded):
            path = templates_dir / name
            if not path.exists():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for ref in _INCLUDE_RE.findall(content):
                ref_norm = _norm(ref)
                if ref_norm in all_templates and ref_norm not in expanded:
                    expanded.add(ref_norm)
                    changed = True
    return expanded


def get_template_coverage():
    templates_dir = PROJECT_ROOT / "templates"
    all_templates: set[str] = set()
    for t in templates_dir.rglob("*.html"):
        all_templates.add(_norm(str(t.relative_to(templates_dir))))

    rendered = _collect_rendered_templates()
    expanded = _expand_includes(rendered, all_templates)

    pct = (len(expanded) / len(all_templates) * 100) if all_templates else 0
    return all_templates, expanded, pct


# ── Frontend JS coverage ──────────────────────────────────────────────────


def get_js_coverage(rendered_templates: set[str]):
    js_dir = PROJECT_ROOT / "static" / "js"
    all_js: set[str] = set()
    for jf in js_dir.rglob("*.js"):
        all_js.add(_norm(str(jf.relative_to(js_dir))))

    referenced: set[str] = set()
    templates_dir = PROJECT_ROOT / "templates"
    for name in rendered_templates:
        path = templates_dir / name
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in _SCRIPT_RE.findall(content):
            if "/static/js/" in m:
                js_rel = m.split("/static/js/")[-1]
                referenced.add(_norm(js_rel))
            elif m.startswith("static/js/"):
                js_rel = m[len("static/js/") :]
                referenced.add(_norm(js_rel))
    return all_js, referenced


# ── Report formatting ─────────────────────────────────────────────────────


def _pct(pct: float) -> str:
    if pct >= 80:
        icon = "🟢"
    elif pct >= 50:
        icon = "🟡"
    else:
        icon = "🔴"
    return f"{icon} {pct:.1f}%"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    backend = get_backend_coverage()

    def _iter_lines():
        yield "## 📊 نظام التغطية الشاملة — Comprehensive Coverage Report"
        yield ""

        # ── Backend ──
        if backend:
            yield "### Backend (Python) — التغطية حسب الفئة"
            yield ""
            yield "| الفئة (Component) | الملفات | التعليمات | المغطاة | النسبة |"
            yield "|------------------|---------|-----------|---------|--------|"
            for _key, label, files, total, covered, pct in backend:
                yield f"| {label} | {files} | {total} | {covered} | {_pct(pct)} |"
            yield ""
        else:
            yield "### Backend (Python) — ⚠️ لا توجد بيانات تغطية"
            yield ""

        # ── Templates ──
        all_templates, rendered_templates, tmpl_pct = get_template_coverage()
        yield "### Frontend (Templates) — تغطية القوالب"
        yield ""
        yield f"- إجمالي القوالب: **{len(all_templates)}**"
        yield f"- القوالب المُقدّمة أثناء الاختبارات: **{len(rendered_templates)}**"
        yield f"- نسبة التغطية: **{_pct(tmpl_pct)}**"
        yield ""

        # ── JS ──
        all_js, js_ref = get_js_coverage(rendered_templates)
        js_pct = (len(js_ref) / len(all_js) * 100) if all_js else 0
        yield "### Frontend (JavaScript) — تغطية ملفات JS"
        yield ""
        yield f"- إجمالي ملفات JS: **{len(all_js)}**"
        yield f"- ملفات JS مُحمّلة عبر قوالب تم اختبارها: **{len(js_ref)}**"
        yield f"- نسبة الوصول (reachability): **{_pct(js_pct)}**"
        yield "- ⚠️ لا يوجد إطار اختبار JS (jest/vitest)، التغطية الفعلية = **0%**"
        yield ""

        # ── Summary table ──
        yield "### الملخص الإجمالي — Overall Summary"
        yield ""
        if backend:
            overall_pct = next((b[5] for b in backend if b[0] == "_overall"), 0)
            combined = overall_pct * 0.60 + tmpl_pct * 0.25 + 0 * 0.15
            yield "| الطبقة (Layer) | النسبة (Coverage) |"
            yield "|---------------|-------------------|"
            yield f"| Backend (Python) | {_pct(overall_pct)} |"
            yield f"| Frontend (Templates) | {_pct(tmpl_pct)} |"
            yield f"| Frontend (JS reachability) | {_pct(js_pct)} |"
            yield "| Frontend (JS test coverage) | 🔴 0.0% |"
            yield f"| **النظام ككل (weighted: 60/25/15)** | **{_pct(combined)}** |"
            yield ""
        else:
            yield "لا توجد بيانات تغطية كافية لعرض الملخص."
            yield ""

        # ── Missing templates (top 30) ──
        missing = sorted(all_templates - rendered_templates)
        if missing:
            yield "### قوالب غير مُغطاة — Uncovered Templates (top 30)"
            yield ""
            for t in missing[:30]:
                yield f"- `{t}`"
            if len(missing) > 30:
                yield f"- ... و {len(missing) - 30} قوالب أخرى"
            yield ""

    lines: list[str] = list(_iter_lines())
    output = "\n".join(lines)
    print(output)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(output + "\n")

    return 0 if backend else 1


if __name__ == "__main__":
    sys.exit(main())
