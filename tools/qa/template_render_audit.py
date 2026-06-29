"""
Template & page render audit — local smoke for every HTML template route.

Run: python tools/qa/template_render_audit.py
     python tools/qa/template_render_audit.py --no-bootstrap
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("SKIP_SYSTEM_INTEGRITY", "1")

from dotenv import load_dotenv

load_dotenv(_ROOT / ".env")

QA_TENANT_SLUG = "qa-template-audit"
QA_MARKER = "[TEMPLATE-AUDIT]"


@dataclass
class Finding:
    kind: str  # static | route | template
    target: str
    ok: bool
    status: int | None = None
    detail: str = ""


@dataclass
class AuditReport:
    findings: list[Finding] = field(default_factory=list)

    def add(self, **kwargs):
        self.findings.append(Finding(**kwargs))

    @property
    def failed(self):
        return [f for f in self.findings if not f.ok]


def _login(client, app, username: str = "owner", tenant_id: int | None = None):
    from models.user import User
    from utils.tenanting import ACTIVE_TENANT_SESSION_KEY

    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            raise RuntimeError(f"user not found: {username}")
        uid = str(user.id)
    with client.session_transaction() as sess:
        sess.clear()
        sess["_user_id"] = uid
        sess["_fresh"] = True
        if tenant_id is not None:
            sess[ACTIVE_TENANT_SESSION_KEY] = tenant_id


def bootstrap_qa_tenant(app) -> int | None:
    from extensions import db
    from models import Branch, Warehouse
    from models.tenant import Tenant
    from services.gl_service import GLService
    from utils.tenanting import without_tenant_scope

    with app.app_context():
        with without_tenant_scope():
            tenant = Tenant.query.filter_by(slug=QA_TENANT_SLUG).first()
            if not tenant:
                tenant = Tenant(
                    name=f"{QA_MARKER} QA Tenant",
                    name_ar="شركة فحص القوالب",
                    name_en="Template Audit QA",
                    slug=QA_TENANT_SLUG,
                    default_currency="AED",
                    is_active=True,
                    is_suspended=False,
                )
                db.session.add(tenant)
                db.session.flush()
            branch = Branch.query.filter_by(tenant_id=tenant.id, is_main=True).first()
            if not branch:
                branch = Branch(
                    tenant_id=tenant.id,
                    name="Main",
                    code="MAIN",
                    city="HQ",
                    is_main=True,
                    is_active=True,
                )
                db.session.add(branch)
                db.session.flush()
            wh = Warehouse.query.filter_by(tenant_id=tenant.id, is_main=True).first()
            if not wh:
                wh = Warehouse(
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    name="Main WH",
                    name_ar="المستودع الرئيسي",
                    code="WH-MAIN",
                    is_main=True,
                    is_active=True,
                )
                db.session.add(wh)
            db.session.commit()
            GLService.ensure_core_accounts(tenant_id=tenant.id, cleanup_extra=False)
            db.session.commit()
            return tenant.id


def audit_static_templates(report: AuditReport):
    templates_dir = _ROOT / "templates"
    all_html = {p.relative_to(templates_dir).as_posix() for p in templates_dir.rglob("*.html")}
    extend_re = re.compile(r"""{%\s*extends\s+['"]([^'"]+)['"]""")
    include_re = re.compile(r"""{%\s*include\s+['"]([^'"]+)['"]""")

    for path in sorted(all_html):
        full = templates_dir / path
        try:
            text = full.read_text(encoding="utf-8")
        except Exception as e:
            report.add(kind="static", target=str(path), ok=False, detail=str(e))
            continue
        for ref in extend_re.findall(text) + include_re.findall(text):
            ref_path = ref.replace("/", os.sep)
            candidates = [
                templates_dir / ref_path,
                templates_dir / f"{ref_path}.html",
            ]
            if not any(c.is_file() for c in candidates):
                report.add(
                    kind="static",
                    target=str(path),
                    ok=False,
                    detail=f"missing include/extends: {ref}",
                )
    ok_count = len(all_html) - len([f for f in report.findings if f.kind == "static" and not f.ok])
    report.add(kind="static", target=f"summary/{len(all_html)}_templates", ok=True, detail=f"checked {len(all_html)} files, issues above")


def _first_id(model):
    from extensions import db
    row = db.session.query(model).order_by(model.id.asc()).first()
    return row.id if row else None


def _url_values(rule) -> dict | None:
    """Best-effort path parameter values for GET smoke (call inside app_context)."""
    from models import (
        Branch, Customer, Product, Sale, Supplier, User, Warehouse,
    )
    from models.tenant import Tenant

    hints: dict[str, object] = {
        "tenant_id": _first_id(Tenant),
        "branch_id": _first_id(Branch),
        "warehouse_id": _first_id(Warehouse),
        "id": None,
        "user_id": _first_id(User),
        "product_id": _first_id(Product),
        "customer_id": _first_id(Customer),
        "supplier_id": _first_id(Supplier),
        "sale_id": _first_id(Sale),
    }

    values = {}
    for arg in rule.arguments:
        if arg in hints and hints[arg] is not None:
            values[arg] = hints[arg]
        elif arg == "id":
            values[arg] = 1
        elif arg.endswith("_id"):
            values[arg] = 1
        else:
            values[arg] = "test"
    return dict(rule.defaults or {}) | values


def audit_routes(app, report: AuditReport, tenant_id: int | None):
    client = app.test_client()
    _login(client, app, tenant_id=tenant_id)

    skip_prefixes = ("/static/",)
    skip_endpoints = {"static"}

    tested = 0
    with app.app_context():
        rules = list(app.url_map.iter_rules())

    for rule in sorted(rules, key=lambda r: r.rule):
        if rule.endpoint in skip_endpoints:
            continue
        if not rule.methods or "GET" not in rule.methods:
            continue
        if any(rule.rule.startswith(p) for p in skip_prefixes):
            continue
        if "<path:" in rule.rule:
            continue

        try:
            with app.app_context():
                values = _url_values(rule)
                built = rule.build(values) if values is not None else rule.rule
                url = built[1] if isinstance(built, tuple) else built
        except Exception as e:
            report.add(kind="route", target=rule.rule, ok=False, detail=f"build failed: {e}")
            continue

        try:
            resp = client.get(url, follow_redirects=True)
            tested += 1
            ok = resp.status_code < 500
            detail = ""
            body = resp.get_data(as_text=True)
            if resp.status_code >= 500:
                detail = "server error"
            elif "Traceback" in body:
                ok = False
                detail = "traceback in body"
            elif "حدث خطأ غير متوقع" in body:
                ok = False
                detail = "generic error page"
            report.add(
                kind="route",
                target=f"{rule.rule} [{rule.endpoint}]",
                ok=ok,
                status=resp.status_code,
                detail=detail,
            )
        except Exception as e:
            report.add(
                kind="route",
                target=f"{rule.rule} [{rule.endpoint}]",
                ok=False,
                detail=str(e),
            )

    report.add(kind="route", target="summary", ok=True, detail=f"tested {tested} GET routes")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-bootstrap", action="store_true")
    parser.add_argument("--json-out", default="tools/qa/template_render_audit_report.json")
    args = parser.parse_args()

    from app import create_app

    app = create_app()
    report = AuditReport()

    tenant_id = None
    if not args.no_bootstrap:
        try:
            tenant_id = bootstrap_qa_tenant(app)
            print(f"QA tenant ready id={tenant_id} slug={QA_TENANT_SLUG}")
        except Exception as e:
            print(f"WARN bootstrap: {e}")
            traceback.print_exc()
    else:
        from models.tenant import Tenant
        with app.app_context():
            t = Tenant.query.filter_by(slug=QA_TENANT_SLUG).first()
            tenant_id = t.id if t else None

    print("Static template scan...")
    audit_static_templates(report)

    print("Route render scan...")
    audit_routes(app, report, tenant_id)

    out_path = _ROOT / args.json_out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "failed_count": len(report.failed),
        "total": len(report.findings),
        "failed": [asdict(f) for f in report.failed],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== TEMPLATE AUDIT ===")
    print(f"Total findings: {len(report.findings)}")
    print(f"Failures: {len(report.failed)}")
    print(f"Report: {out_path}")
    for f in report.failed[:40]:
        print(f"  FAIL [{f.kind}] {f.target} status={f.status} — {f.detail}")
    if len(report.failed) > 40:
        print(f"  ... and {len(report.failed) - 40} more")

    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
