"""
AI Security Check - Static analysis of AI endpoint security.

This script performs static code analysis on routes/ai.py to verify:
- All endpoints have appropriate permission decorators
- CSRF protection is applied where needed
- Login requirements are enforced
- No endpoints are left unprotected

Run: python tools/qa/ai_security_check.py
"""
import ast
import os
import sys
from dataclasses import dataclass
from typing import List, Dict, Set

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


@dataclass
class EndpointInfo:
    route: str
    methods: List[str]
    has_login_required: bool
    has_permission: bool
    has_owner_required: bool
    has_admin_required: bool
    has_csrf_exempt: bool
    permission_name: str = ""
    line_number: int = 0


class AISecurityChecker(ast.NodeVisitor):
    def __init__(self):
        self.endpoints: List[EndpointInfo] = []
        self.current_decorators: List[str] = []
        self.current_route = ""
        self.current_methods: List[str] = []
        self.current_line = 0

    def visit_FunctionDef(self, node):
        # Check for route decorator
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Attribute):
                    if decorator.func.attr == "route":
                        self.current_route = decorator.args[0].value if decorator.args else ""
                        if len(decorator.args) > 1 and isinstance(decorator.args[1], ast.Constant):
                            self.current_methods = [decorator.args[1].value]
                        else:
                            self.current_methods = ["GET"]
                        self.current_line = node.lineno
                    elif decorator.func.attr == "exempt":
                        self.current_decorators.append("csrf_exempt")
            elif isinstance(decorator, ast.Name):
                if decorator.id == "login_required":
                    self.current_decorators.append("login_required")
                elif decorator.id == "owner_required":
                    self.current_decorators.append("owner_required")
                elif decorator.id == "admin_required":
                    self.current_decorators.append("admin_required")

        # Check for permission_required decorator
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name):
                    if decorator.func.id == "permission_required":
                        if decorator.args and isinstance(decorator.args[0], ast.Constant):
                            self.current_decorators.append(f"permission_required({decorator.args[0].value})")

        # Create endpoint info if we have a route
        if self.current_route:
            endpoint = EndpointInfo(
                route=self.current_route,
                methods=self.current_methods,
                has_login_required="login_required" in self.current_decorators,
                has_permission=any("permission_required" in d for d in self.current_decorators),
                permission_name=next((d for d in self.current_decorators if "permission_required" in d), ""),
                has_owner_required="owner_required" in self.current_decorators,
                has_admin_required="admin_required" in self.current_decorators,
                has_csrf_exempt="csrf_exempt" in self.current_decorators,
                line_number=self.current_line,
            )
            self.endpoints.append(endpoint)

        # Reset for next function
        self.current_route = ""
        self.current_methods = []
        self.current_decorators = []
        self.current_line = 0

        self.generic_visit(node)


def check_ai_routes() -> Dict:
    """Analyze routes/ai.py for security issues."""
    ai_routes_path = os.path.join(os.path.dirname(__file__), "..", "..", "routes", "ai.py")
    
    if not os.path.exists(ai_routes_path):
        return {
            "status": "FAIL",
            "error": f"routes/ai.py not found at {ai_routes_path}"
        }

    with open(ai_routes_path, "r", encoding="utf-8") as f:
        code = f.read()

    tree = ast.parse(code)
    checker = AISecurityChecker()
    checker.visit(tree)

    issues = []
    warnings = []
    unprotected = []
    
    for endpoint in checker.endpoints:
        # Check if endpoint is unprotected
        if not endpoint.has_login_required and not endpoint.has_owner_required:
            unprotected.append(endpoint.route)
            issues.append(f"Endpoint {endpoint.route} has no login_required or owner_required decorator")
        
        # Check if POST endpoint lacks permission
        if "POST" in endpoint.methods and not endpoint.has_permission and not endpoint.has_owner_required and not endpoint.has_admin_required:
            issues.append(f"POST endpoint {endpoint.route} lacks permission decorator")
        
        # Warn about CSRF exempt on POST endpoints
        if "POST" in endpoint.methods and endpoint.has_csrf_exempt:
            warnings.append(f"POST endpoint {endpoint.route} is CSRF exempt (line {endpoint.line_number})")

    return {
        "status": "PASS" if not issues else "FAIL",
        "total_endpoints": len(checker.endpoints),
        "unprotected_count": len(unprotected),
        "unprotected": unprotected,
        "issues": issues,
        "warnings": warnings,
        "endpoints": [
            {
                "route": e.route,
                "methods": e.methods,
                "protected": e.has_login_required or e.has_owner_required,
                "permission": e.permission_name,
                "csrf_exempt": e.has_csrf_exempt,
            }
            for e in checker.endpoints
        ]
    }


def main():
    result = check_ai_routes()
    
    print("=" * 60)
    print("AI SECURITY CHECK - Static Analysis")
    print("=" * 60)
    print(f"Status: {result['status']}")
    print(f"Total Endpoints: {result['total_endpoints']}")
    print(f"Unprotected Endpoints: {result['unprotected_count']}")
    
    if result.get("error"):
        print(f"Error: {result['error']}")
        return 1
    
    if result["issues"]:
        print("\n❌ ISSUES FOUND:")
        for issue in result["issues"]:
            print(f"  - {issue}")
    
    if result["warnings"]:
        print("\n⚠️  WARNINGS:")
        for warning in result["warnings"]:
            print(f"  - {warning}")
    
    if result["unprotected"]:
        print(f"\n🔓 Unprotected Endpoints: {', '.join(result['unprotected'])}")
    
    print("\n📋 Endpoint Summary:")
    for ep in result["endpoints"]:
        status = "✅" if ep["protected"] else "❌"
        csrf = " (CSRF exempt)" if ep["csrf_exempt"] else ""
        print(f"  {status} {ep['route']} ({', '.join(ep['methods'])}) - {ep['permission'] or 'no permission'}{csrf}")
    
    print("=" * 60)
    
    if result["status"] == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
