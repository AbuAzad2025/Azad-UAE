"""Permission Consistency Audit — C3 Automation."""
import ast
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class RouteInfo:
    endpoint: str
    function_name: str
    login_required: bool = False
    permission_codes: List[str] = field(default_factory=list)
    decorator_types: Set[str] = field(default_factory=set)
    rendered_templates: List[str] = field(default_factory=list)
    file_path: str = ""
    line_number: int = 0


@dataclass
class TemplateLink:
    endpoint: str
    raw_line: str
    has_login_check: bool = False
    permission_conditions: List[str] = field(default_factory=list)
    file_path: str = ""
    line_number: int = 0


@dataclass
class Gap:
    endpoint: str
    category: str
    route_guards: List[str] = field(default_factory=list)
    template_conditions: List[str] = field(default_factory=list)
    severity: str = "low"
    file_path: str = ""
    line_number: int = 0


@dataclass
class AuditReport:
    routes: List[RouteInfo] = field(default_factory=list)
    templates: List[TemplateLink] = field(default_factory=list)
    gaps: List[Gap] = field(default_factory=list)
    safe_count: int = 0
    gap_count: int = 0
    hidden_count: int = 0
    unauth_count: int = 0


_ROUTE_DECORATOR_PATTERNS = {
    "login_required": re.compile(r"@login_required"),
    "permission_required": re.compile(r"@permission_required\(['\"](.+?)['\"]\)"),
    "any_permission_required": re.compile(r"@any_permission_required\((.*?)\)"),
    "admin_required": re.compile(r"@admin_required"),
    "owner_required": re.compile(r"@owner_required"),
    "owner_only": re.compile(r"@owner_only"),
    "seller_or_above": re.compile(r"@seller_or_above"),
    "super_admin_required": re.compile(r"@super_admin_required"),
    "platform_owner_required": re.compile(r"@platform_owner_required"),
    "company_admin_required": re.compile(r"@company_admin_required"),
    "owner_or_company_admin": re.compile(r"@owner_or_company_admin"),
    "branch_manager_required": re.compile(r"@branch_manager_required"),
    "accountant_required": re.compile(r"@accountant_required"),
}


class RouteAnalyzer:
    def __init__(self, routes_dir: str):
        self.routes_dir = routes_dir
        self.blueprint_map: Dict[str, str] = {}

    def analyze(self) -> List[RouteInfo]:
        results: List[RouteInfo] = []
        for root, _, files in os.walk(self.routes_dir):
            for fname in files:
                if not fname.endswith(".py") or fname.startswith("__"):
                    continue
                fpath = os.path.join(root, fname)
                results.extend(self._analyze_file(fpath))
        return results

    def _analyze_file(self, fpath: str) -> List[RouteInfo]:
        with open(fpath, "r", encoding="utf-8") as fh:
            source = fh.read()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        bp_names = self._extract_blueprints(tree)
        routes: List[RouteInfo] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                route = self._inspect_function(node, bp_names, fpath)
                if route:
                    routes.append(route)
        return routes

    def _extract_blueprints(self, tree: ast.AST) -> Dict[str, str]:
        bp_map: Dict[str, str] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if not isinstance(node.value, ast.Call):
                    continue
                func = node.value.func
                is_bp = False
                if isinstance(func, ast.Name) and func.id == "Blueprint":
                    is_bp = True
                elif isinstance(func, ast.Attribute) and func.attr == "Blueprint":
                    is_bp = True
                if not is_bp:
                    continue
                if node.value.args and isinstance(node.value.args[0], ast.Constant):
                    bp_map[target.id] = str(node.value.args[0].value)
                for kw in node.value.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                        bp_map[target.id] = str(kw.value.value)
        return bp_map

    def _inspect_function(self, node: ast.FunctionDef, bp_map: Dict[str, str], fpath: str) -> Optional[RouteInfo]:
        blueprint_name = None
        for dec in node.decorator_list:
            call_name = self._call_name(dec)
            if not call_name:
                continue
            for bp_var, bp_name in bp_map.items():
                if call_name.startswith(bp_var + ".route"):
                    blueprint_name = bp_name
                    break
        if not blueprint_name:
            return None
        info = RouteInfo(
            endpoint=f"{blueprint_name}.{node.name}",
            function_name=node.name,
            file_path=fpath,
            line_number=node.lineno,
        )
        for dec in node.decorator_list:
            call_name = self._call_name(dec)
            if not call_name:
                continue
            if "login_required" in call_name:
                info.login_required = True
            elif "permission_required" in call_name and "any_permission" not in call_name:
                codes = self._extract_permission_args(dec)
                info.permission_codes.extend(codes)
            elif "any_permission_required" in call_name:
                codes = self._extract_permission_args(dec)
                info.permission_codes.extend(codes)
                info.decorator_types.add("any_permission_required")
            elif "admin_required" in call_name:
                info.decorator_types.add("admin_required")
            elif "owner_required" in call_name:
                info.decorator_types.add("owner_required")
            elif "owner_only" in call_name:
                info.decorator_types.add("owner_only")
            elif "seller_or_above" in call_name:
                info.decorator_types.add("seller_or_above")
            elif "super_admin_required" in call_name:
                info.decorator_types.add("super_admin_required")
            elif "platform_owner_required" in call_name:
                info.decorator_types.add("platform_owner_required")
            elif "company_admin_required" in call_name:
                info.decorator_types.add("company_admin_required")
            elif "owner_or_company_admin" in call_name:
                info.decorator_types.add("owner_or_company_admin")
            elif "branch_manager_required" in call_name:
                info.decorator_types.add("branch_manager_required")
            elif "accountant_required" in call_name:
                info.decorator_types.add("accountant_required")
        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Call):
                cname = self._call_name(stmt)
                if cname in ("render_template", "flask.render_template"):
                    if stmt.args and isinstance(stmt.args[0], ast.Constant):
                        info.rendered_templates.append(str(stmt.args[0].value))
        return info

    def _call_name(self, node: ast.expr) -> str:
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                base = self._attr_chain(node.func)
                return base
            if isinstance(node.func, ast.Name):
                return node.func.id
        if isinstance(node, ast.Name):
            return node.id
        return ""

    def _attr_chain(self, node: ast.Attribute) -> str:
        parts: List[str] = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))

    def _extract_permission_args(self, node: ast.Call) -> List[str]:
        codes: List[str] = []
        for arg in node.args:
            if isinstance(arg, ast.Constant):
                codes.append(str(arg.value))
            elif isinstance(arg, ast.Tuple):
                for elt in arg.elts:
                    if isinstance(elt, ast.Constant):
                        codes.append(str(elt.value))
        return codes


class TemplateAnalyzer:
    _URL_FOR = re.compile(r"url_for\(['\"](.+?)['\"]")
    _HAS_PERMISSION = re.compile(r"has_permission\(['\"](.+?)['\"]\)")
    _IS_OWNER = re.compile(r"current_user\.is_owner")
    _IS_ADMIN = re.compile(r"current_user\.is_admin")
    _IS_AUTHENTICATED = re.compile(r"current_user\.is_authenticated")
    _IF_AUTH = re.compile(r"{%\s*if\s+current_user\.is_authenticated\s*%}")

    def __init__(self, templates_dir: str):
        self.templates_dir = templates_dir

    def analyze(self) -> List[TemplateLink]:
        results: List[TemplateLink] = []
        for root, _, files in os.walk(self.templates_dir):
            for fname in files:
                if not fname.endswith(".html"):
                    continue
                fpath = os.path.join(root, fname)
                results.extend(self._analyze_file(fpath))
        return results

    def _analyze_file(self, fpath: str) -> List[TemplateLink]:
        with open(fpath, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        links: List[TemplateLink] = []
        scope_stack: List[Tuple[bool, List[str]]] = []
        scope_login = False
        scope_perms: List[str] = []
        for lineno, raw in enumerate(lines, start=1):
            line = raw.strip()
            if line.startswith("{% if "):
                matches = self._HAS_PERMISSION.findall(line)
                if self._IS_OWNER.search(line):
                    matches.append("is_owner")
                if self._IS_ADMIN.search(line):
                    matches.append("is_admin")
                login = bool(self._IS_AUTHENTICATED.search(line))
                scope_stack.append((login, list(matches)))
                scope_login = any(s[0] for s in scope_stack)
                scope_perms = []
                for s in scope_stack:
                    scope_perms.extend(s[1])
            if line.startswith("{% endif %}"):
                if scope_stack:
                    scope_stack.pop()
                scope_login = any(s[0] for s in scope_stack)
                scope_perms = []
                for s in scope_stack:
                    scope_perms.extend(s[1])
            for endpoint in self._URL_FOR.findall(line):
                inline_perms = list(dict.fromkeys(scope_perms))
                inline_has = self._HAS_PERMISSION.findall(line)
                if inline_has:
                    inline_perms.extend(inline_has)
                if self._IS_OWNER.search(line):
                    inline_perms.append("is_owner")
                if self._IS_ADMIN.search(line):
                    inline_perms.append("is_admin")
                links.append(TemplateLink(
                    endpoint=endpoint,
                    raw_line=line[:120],
                    has_login_check=scope_login or bool(self._IS_AUTHENTICATED.search(line)),
                    permission_conditions=list(dict.fromkeys(inline_perms)),
                    file_path=fpath,
                    line_number=lineno,
                ))
        return links


class PermissionMatcher:
    _TMPL_COUNT_THRESHOLD = 10

    def match(
        self, routes: List[RouteInfo], templates: List[TemplateLink],
        template_guards: Dict[str, Set[str]] = None,
        template_endpoint_count: Dict[str, int] = None,
    ) -> AuditReport:
        route_map: Dict[str, RouteInfo] = {r.endpoint: r for r in routes}
        template_map: Dict[str, List[TemplateLink]] = {}
        for t in templates:
            template_map.setdefault(t.endpoint, []).append(t)
        report = AuditReport(routes=routes, templates=templates)
        tg = template_guards or {}
        tec = template_endpoint_count or {}
        for endpoint, route in route_map.items():
            route_guards = self._route_guards(route)
            links = template_map.get(endpoint, [])
            if not links:
                if route_guards:
                    report.hidden_count += 1
                    report.gaps.append(Gap(
                        endpoint=endpoint,
                        category="HIDDEN",
                        route_guards=route_guards,
                        severity="low",
                        file_path=route.file_path,
                        line_number=route.line_number,
                    ))
                continue
            for link in links:
                if not route_guards:
                    if link.has_login_check:
                        report.unauth_count += 1
                        report.gaps.append(Gap(
                            endpoint=endpoint,
                            category="UNAUTH",
                            route_guards=[],
                            template_conditions=["is_authenticated"],
                            severity="medium",
                            file_path=link.file_path,
                            line_number=link.line_number,
                        ))
                    else:
                        report.safe_count += 1
                    continue
                if self._tmpl_covers(link.file_path, route_guards, tg, tec):
                    report.safe_count += 1
                    continue
                if route.permission_codes:
                    if self._perm_match(route.permission_codes, link.permission_conditions):
                        report.safe_count += 1
                    else:
                        report.gap_count += 1
                        report.gaps.append(Gap(
                            endpoint=endpoint,
                            category="GAP",
                            route_guards=route_guards,
                            template_conditions=link.permission_conditions or ["none"],
                            severity="high" if "owner" not in endpoint else "medium",
                            file_path=link.file_path,
                            line_number=link.line_number,
                        ))
                else:
                    if link.has_login_check or route.login_required:
                        report.safe_count += 1
                    elif "is_owner" in link.permission_conditions and ("owner_only" in route.decorator_types or "owner_required" in route.decorator_types):
                        report.safe_count += 1
                    elif "is_admin" in link.permission_conditions and "admin_required" in route.decorator_types:
                        report.safe_count += 1
                    else:
                        report.gap_count += 1
                        report.gaps.append(Gap(
                            endpoint=endpoint,
                            category="GAP",
                            route_guards=route_guards,
                            template_conditions=link.permission_conditions or ["none"],
                            severity="medium",
                            file_path=link.file_path,
                            line_number=link.line_number,
                        ))
        return report

    def _tmpl_covers(
        self, file_path: str, route_guards: List[str],
        template_guards: Dict[str, Set[str]],
        template_endpoint_count: Dict[str, int],
    ) -> bool:
        tname = file_path.replace(os.sep, "/")
        idx = tname.rfind("templates/")
        if idx != -1:
            tname = tname[idx + len("templates/"):]
        count = template_endpoint_count.get(tname, 0)
        if count == 0:
            return False
        if count > self._TMPL_COUNT_THRESHOLD:
            return False
        tguards = template_guards.get(tname, set())
        if not tguards:
            return False
        return set(route_guards).issubset(tguards)

    def _route_guards(self, route: RouteInfo) -> List[str]:
        guards: List[str] = []
        if route.login_required:
            guards.append("login_required")
        guards.extend(route.permission_codes)
        guards.extend(route.decorator_types)
        return guards

    def _perm_match(self, route_codes: List[str], tmpl_codes: List[str]) -> bool:
        if not route_codes:
            return True
        if not tmpl_codes:
            return False
        rc = set(route_codes)
        tc = set(tmpl_codes)
        if "is_owner" in tc and ("owner_only" in rc or "owner_required" in rc):
            return True
        if "is_admin" in tc and "admin_required" in rc:
            return True
        return bool(rc & tc)


class AuditReporter:
    def to_markdown(self, report: AuditReport) -> str:
        lines = [
            "# Permission Consistency Audit Report\n",
            f"**Routes scanned:** {len(report.routes)}  ",
            f"**Template links scanned:** {len(report.templates)}  ",
            f"**Safe:** {report.safe_count}  ",
            f"**Gaps:** {report.gap_count}  ",
            f"**Hidden:** {report.hidden_count}  ",
            f"**Unauth:** {report.unauth_count}  ",
            "\n---\n",
        ]
        if not report.gaps:
            lines.append("\n✅ No gaps detected.\n")
            return "\n".join(lines)
        for severity in ("high", "medium", "low"):
            sev_gaps = [g for g in report.gaps if g.severity == severity]
            if not sev_gaps:
                continue
            lines.append(f"\n## {severity.upper()} Severity ({len(sev_gaps)})\n")
            for g in sev_gaps:
                lines.append(f"- **`{g.endpoint}`** — {g.category}")
                lines.append(f"  - Route guards: {', '.join(g.route_guards) or 'none'}")
                lines.append(f"  - Template: {g.file_path}:{g.line_number}")
                lines.append(f"  - Template conditions: {', '.join(g.template_conditions)}")
                lines.append("")
        return "\n".join(lines)


def run_audit(routes_dir: str, templates_dir: str, output_path: Optional[str] = None) -> AuditReport:
    routes = RouteAnalyzer(routes_dir).analyze()
    templates = TemplateAnalyzer(templates_dir).analyze()
    template_guards: Dict[str, Set[str]] = {}
    template_endpoint_count: Dict[str, int] = {}
    for route in routes:
        for tmpl in route.rendered_templates:
            template_endpoint_count[tmpl] = template_endpoint_count.get(tmpl, 0) + 1
            guards = template_guards.setdefault(tmpl, set())
            guards.update(route.permission_codes)
            if route.login_required:
                guards.add("login_required")
            guards.update(route.decorator_types)
    report = PermissionMatcher().match(routes, templates, template_guards, template_endpoint_count)
    report.gaps.sort(key=lambda g: (g.severity != "high", g.severity != "medium", g.endpoint))
    md = AuditReporter().to_markdown(report)
    if output_path:
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(md)
    return report


if __name__ == "__main__":
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    routes_dir = os.path.join(root, "routes")
    templates_dir = os.path.join(root, "templates")
    output_path = os.path.join(root, "docs", "PERMISSION_AUDIT_REPORT.md")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    report = run_audit(routes_dir, templates_dir, output_path)
    print(f"Routes: {len(report.routes)} | Templates: {len(report.templates)}")
    print(f"Safe: {report.safe_count} | Gaps: {report.gap_count}")
    print(f"Hidden: {report.hidden_count} | Unauth: {report.unauth_count}")
    print(f"Report written to {output_path}")
    sys.exit(0 if report.gap_count == 0 else 1)
