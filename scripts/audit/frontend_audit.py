#!/usr/bin/env python3
"""Frontend audit scanner — finds defect classes the CI gates do NOT cover.

Existing gates (do not duplicate): biome (static/js lint+format),
stylelint (static/**/*.css style), scripts/lint/check_templates.py (Jinja
syntax), scripts/check_strict_i18n.py (i18n coverage).

This scanner targets the gaps:
  Templates : inline event handlers, `var`/console.log/eval inside inline
              <script>, POST <form> blocks missing csrf_token, <img> without
              alt, duplicate static id= values, references to missing static
              assets, <html> without explicit dir/lang conditional blocks.
  JS files  : console.log / document.write / eval / var (biome covers some;
              reported here so template+JS results are comparable).
  CSS files : !important usage, duplicate selectors within a file, ID
              selectors.

Report-only: exits 0 unless --strict is passed with findings present.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VENDOR_DIRS = ("adminlte", "datatables", "theme")

Findings = dict[str, list[tuple[str, int, str]]]

EVENT_ATTR = re.compile(
    r"\son(click|dblclick|change|submit|input|keyup|keydown|keypress|"
    r"mouseover|mouseout|mouseenter|mouseleave|load|error|focus|blur|"
    r"contextmenu|touchstart|touchend|scroll|resize)\s*=",
    re.IGNORECASE,
)
VAR_DECL = re.compile(r"(?<![\w$.])var\s+[A-Za-z_$]")
CONSOLE_LOG = re.compile(r"\bconsole\.log\s*\(")
BAD_APIS = re.compile(r"\b(document\.write|eval)\s*\(")
IMG_NO_ALT = re.compile(r"<img\b(?![^>]*\balt\s*=)[^>]*>", re.IGNORECASE)
ID_ATTR = re.compile(r'(?<![-\w])id\s*=\s*"([^"{%]+)"')
FORM_BLOCK = re.compile(r"<form\b.*?</form>", re.IGNORECASE | re.DOTALL)
METHOD_POST = re.compile(r'\bmethod\s*=\s*["\']?post\b', re.IGNORECASE)
CSRF_TOKEN = re.compile(r"csrf_token|hidden_tag\s*\(")
STATIC_REF = re.compile(
    r"url_for\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"]+)['\"]"
)
HTML_TAG = re.compile(r"<html\b[^>]*>", re.IGNORECASE)
DIR_COND = re.compile(r"\{%\s*if[^%]*%\}\s*dir\s*=|dir\s*=\s*\"\{\{")
SCRIPT_BLOCK = re.compile(r"<script\b(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>", re.IGNORECASE | re.DOTALL)
IMPORTANT = re.compile(r"!important\b")
CSS_ID_SELECTOR = re.compile(r"(^|[}\s])#[A-Za-z][\w-]*[\s,{]", re.MULTILINE)
CSS_RULE_START = re.compile(r"^\s*([^{}@/][^{]*)\{", re.MULTILINE)
JQUERY = re.compile(r"(?<![\w$])\$\s*\(")


def is_vendor(path: Path) -> bool:
    return any(part in VENDOR_DIRS for part in path.parts)


def add(findings: Findings, rule: str, path: Path, line: int, detail: str) -> None:
    findings[rule].append((str(path.relative_to(ROOT)), line, detail))


def scan_template(path: Path, text: str, findings: Findings) -> None:
    lines = text.splitlines()
    # Strip script/style bodies for HTML-level checks
    script_spans: list[tuple[int, int]] = []
    for m in SCRIPT_BLOCK.finditer(text):
        script_spans.append((m.start(1), m.end(1)))
        body_line = text.count("\n", 0, m.start(1)) + 1
        for i, sline in enumerate(m.group(1).splitlines()):
            if VAR_DECL.search(sline):
                add(findings, "T2:var-in-inline-js", path, body_line + i, sline.strip()[:80])
            if CONSOLE_LOG.search(sline):
                add(findings, "T3:console-log-inline", path, body_line + i, sline.strip()[:80])
            if BAD_APIS.search(sline):
                add(findings, "T4:eval-or-document-write", path, body_line + i, sline.strip()[:80])

    def in_script(offset: int) -> bool:
        return any(start <= offset < end for start, end in script_spans)

    for m in EVENT_ATTR.finditer(text):
        if not in_script(m.start()):
            line = text.count("\n", 0, m.start()) + 1
            add(findings, "T1:inline-event-handler", path, line, m.group(0).strip())

    for m in FORM_BLOCK.finditer(text):
        block = m.group(0)
        if METHOD_POST.search(block) and not CSRF_TOKEN.search(block):
            line = text.count("\n", 0, m.start()) + 1
            add(findings, "T5:post-form-no-csrf", path, line, block[:70].replace("\n", " "))

    for i, line_text in enumerate(lines, 1):
        for m in IMG_NO_ALT.finditer(line_text):
            add(findings, "T6:img-no-alt", path, i, m.group(0)[:80])

    ids: dict[str, int] = {}
    for m in ID_ATTR.finditer(text):
        value = m.group(1).strip()
        if value and "{{" not in value and "{%" not in value:
            ids.setdefault(value, 0)
            ids[value] += 1
    for value, count in ids.items():
        if count > 1:
            add(findings, "T7:duplicate-id", path, 0, f'id="{value}" x{count}')

    for m in STATIC_REF.finditer(text):
        if not (ROOT / "static" / m.group(1)).exists():
            line = text.count("\n", 0, m.start()) + 1
            add(findings, "T8:missing-static-asset", path, line, m.group(1))

    if "<!DOCTYPE" in text[:200] or "<!doctype" in text[:200]:
        for m in HTML_TAG.finditer(text):
            tag = m.group(0)
            if "dir=" not in tag or not DIR_COND.search(text):
                line = text.count("\n", 0, m.start()) + 1
                add(findings, "T9:html-no-dir-lang-cond", path, line, tag[:80])


def scan_js(path: Path, text: str, findings: Findings) -> None:
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        if VAR_DECL.search(line):
            add(findings, "J1:var-declaration", path, i, line.strip()[:80])
        prev = lines[i - 2] if i >= 2 else ""
        if CONSOLE_LOG.search(line) and "_DEBUG" not in prev:
            add(findings, "J3:console-log", path, i, line.strip()[:80])
        if BAD_APIS.search(line):
            add(findings, "J4:eval-or-document-write", path, i, line.strip()[:80])
    jquery_hits = len(JQUERY.findall(text))
    if jquery_hits:
        add(findings, "J10:jquery-usage", path, 0, f"{jquery_hits} hits")


def scan_css(path: Path, text: str, findings: Findings) -> None:
    important = len(IMPORTANT.findall(text))
    if important:
        add(findings, "C1:important-usage", path, 0, f"{important} occurrences")
    selectors: dict[str, int] = defaultdict(int)
    for m in CSS_RULE_START.finditer(text):
        sel = " ".join(m.group(1).split())
        if sel and not sel.startswith("@") and len(sel) < 200:
            selectors[sel] += 1
    for sel, count in selectors.items():
        if count > 1:
            add(findings, "C2:duplicate-selector", path, 0, f"{sel[:60]} x{count}")
    id_selectors = len(CSS_ID_SELECTOR.findall(text))
    if id_selectors:
        add(findings, "C3:id-selector", path, 0, f"{id_selectors} hits")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--strict", action="store_true", help="exit 1 on findings")
    args = parser.parse_args()

    findings: Findings = defaultdict(list)

    for path in sorted((ROOT / "templates").rglob("*.html")):
        scan_template(path, path.read_text(encoding="utf-8", errors="replace"), findings)
    for path in sorted((ROOT / "static" / "js").rglob("*.js")):
        if not is_vendor(path):
            scan_js(path, path.read_text(encoding="utf-8", errors="replace"), findings)
    for path in sorted((ROOT / "static").rglob("*.css")):
        if not is_vendor(path):
            scan_css(path, path.read_text(encoding="utf-8", errors="replace"), findings)

    if args.json:
        print(json.dumps({k: v for k, v in sorted(findings.items())}, indent=2))
    else:
        total = 0
        for rule in sorted(findings):
            hits = findings[rule]
            total += len(hits)
            print(f"\n## {rule} — {len(hits)} finding(s)")
            for file, line, detail in hits[:12]:
                loc = f"{file}:{line}" if line else file
                print(f"  {loc}  {detail}")
            if len(hits) > 12:
                print(f"  ... and {len(hits) - 12} more")
        print(f"\nTOTAL: {total} finding(s) across {len(findings)} rule(s)")

    return 1 if args.strict and findings else 0


if __name__ == "__main__":
    sys.exit(main())
