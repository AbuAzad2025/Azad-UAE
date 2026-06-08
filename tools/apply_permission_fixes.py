"""Apply has_permission guards to template gaps from audit report."""
import os
import re
import shutil
from typing import Dict, List, Optional, Tuple


class GapFixer:
    def __init__(self, report_path: str):
        self.report_path = report_path
        self.gaps: List[Dict] = []

    def parse_report(self):
        with open(self.report_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            m = re.search(r"`(.+?)`", line)
            if m and "GAP" in line:
                endpoint = m.group(1)
                if i + 1 < len(lines):
                    guards_line = lines[i + 1]
                    guards = []
                    if "Route guards:" in guards_line:
                        raw = guards_line.split("Route guards:")[1].strip()
                        guards = [g.strip() for g in raw.split(",") if g.strip()]
                if i + 2 < len(lines):
                    tmpl_line = lines[i + 2]
                    tmpl_m = re.search(r"templates\\(.+?):(\d+)", tmpl_line)
                    if tmpl_m:
                        self.gaps.append({
                            "endpoint": endpoint,
                            "guards": guards,
                            "template": tmpl_m.group(1).replace("\\", "/"),
                            "line": int(tmpl_m.group(2)),
                        })
            i += 1

    def fix_all(self, templates_dir: str, dry_run: bool = True) -> int:
        fixed = 0
        for gap in self.gaps:
            perm = self._extract_permission(gap["guards"])
            if not perm:
                continue
            fpath = os.path.join(templates_dir, gap["template"])
            if not os.path.exists(fpath):
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            idx = gap["line"] - 1
            if idx >= len(lines):
                continue
            old_line = lines[idx]
            new_line = self._wrap_line(old_line, perm, gap["endpoint"])
            if new_line and new_line != old_line:
                if not dry_run:
                    lines[idx] = new_line
                    with open(fpath, "w", encoding="utf-8") as f:
                        f.writelines(lines)
                fixed += 1
        return fixed

    def _extract_permission(self, guards: List[str]) -> Optional[str]:
        for g in guards:
            if g.startswith("manage_") or g.startswith("view_"):
                return g
            if g in ("admin_required", "owner_only", "owner_required"):
                return "is_owner"
        return None

    def _wrap_line(self, line: str, perm: str, endpoint: str) -> Optional[str]:
        if perm == "is_owner":
            guard = "{% if current_user.is_owner %}"
            endguard = "{% endif %}"
        else:
            guard = f"{{% if current_user.has_permission('{perm}') %}}"
            endguard = "{% endif %}"
        stripped = line.strip()
        if stripped.startswith("{%") or stripped.startswith("{#"):
            return None
        if "url_for" in stripped:
            indent = line[:len(line) - len(line.lstrip())]
            return f"{indent}{guard}\n{line.rstrip()}\n{indent}{endguard}\n"
        return None


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    report = os.path.join(root, "docs", "PERMISSION_AUDIT_REPORT.md")
    templates = os.path.join(root, "templates")
    fixer = GapFixer(report)
    fixer.parse_report()
    fixed = fixer.fix_all(templates, dry_run=False)
    print(f"Fixed {fixed} gaps out of {len(fixer.gaps)}")
