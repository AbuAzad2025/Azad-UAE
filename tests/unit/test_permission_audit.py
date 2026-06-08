from tools.permission_audit import (
    RouteAnalyzer,
    TemplateAnalyzer,
    PermissionMatcher,
    AuditReporter,
    run_audit,
    RouteInfo,
    TemplateLink,
    Gap,
    AuditReport,
)


class TestRouteAnalyzer:
    def test_blueprint_positional_arg(self, tmp_path):
        f = tmp_path / "test_routes.py"
        f.write_text(
            "from flask import Blueprint\n"
            "bp = Blueprint('sales', __name__)\n"
            "@bp.route('/')\n"
            "@login_required\n"
            "@permission_required('manage_sales')\n"
            "def index(): pass\n"
        )
        routes = RouteAnalyzer(str(tmp_path)).analyze()
        assert len(routes) == 1
        assert routes[0].endpoint == "sales.index"
        assert routes[0].login_required is True
        assert routes[0].permission_codes == ["manage_sales"]

    def test_blueprint_keyword_arg(self, tmp_path):
        f = tmp_path / "test_routes.py"
        f.write_text(
            "from flask import Blueprint\n"
            "bp = Blueprint(name='inventory', import_name=__name__)\n"
            "@bp.route('/items')\n"
            "def items(): pass\n"
        )
        routes = RouteAnalyzer(str(tmp_path)).analyze()
        assert len(routes) == 1
        assert routes[0].endpoint == "inventory.items"
        assert routes[0].login_required is False

    def test_render_template_extraction(self, tmp_path):
        f = tmp_path / "test_routes.py"
        f.write_text(
            "from flask import Blueprint, render_template\n"
            "bp = Blueprint('pos', __name__)\n"
            "@bp.route('/')\n"
            "@login_required\n"
            "@permission_required('manage_sales')\n"
            "def index():\n"
            "    return render_template('pos/index.html')\n"
        )
        routes = RouteAnalyzer(str(tmp_path)).analyze()
        assert routes[0].rendered_templates == ["pos/index.html"]

    def test_admin_owner_decorators(self, tmp_path):
        f = tmp_path / "test_routes.py"
        f.write_text(
            "from flask import Blueprint\n"
            "bp = Blueprint('owner', __name__)\n"
            "@bp.route('/dashboard')\n"
            "@login_required\n"
            "@owner_required\n"
            "def dashboard(): pass\n"
        )
        routes = RouteAnalyzer(str(tmp_path)).analyze()
        assert routes[0].decorator_types == {"owner_required"}


class TestTemplateAnalyzer:
    def test_url_for_extraction(self, tmp_path):
        d = tmp_path / "templates"
        d.mkdir()
        f = d / "base.html"
        f.write_text('<a href="{{ url_for(\'sales.index\') }}">Sales</a>')
        links = TemplateAnalyzer(str(d)).analyze()
        assert len(links) == 1
        assert links[0].endpoint == "sales.index"

    def test_has_permission_scope(self, tmp_path):
        d = tmp_path / "templates"
        d.mkdir()
        f = d / "base.html"
        f.write_text(
            "{% if current_user.has_permission('manage_sales') %}"
            '<a href="{{ url_for(\'sales.create\') }}">New</a>'
            "{% endif %}"
        )
        links = TemplateAnalyzer(str(d)).analyze()
        assert len(links) == 1
        assert links[0].endpoint == "sales.create"
        assert "manage_sales" in links[0].permission_conditions

    def test_is_authenticated_scope(self, tmp_path):
        d = tmp_path / "templates"
        d.mkdir()
        f = d / "base.html"
        f.write_text(
            "{% if current_user.is_authenticated %}"
            '<a href="{{ url_for(\'main.dashboard\') }}">Dash</a>'
            "{% endif %}"
        )
        links = TemplateAnalyzer(str(d)).analyze()
        assert links[0].has_login_check is True


class TestPermissionMatcher:
    def test_safe_exact_permission(self):
        routes = [RouteInfo("sales.create", "create", True, ["manage_sales"])]
        templates = [TemplateLink("sales.create", "", True, ["manage_sales"])]
        report = PermissionMatcher().match(routes, templates)
        assert report.safe_count == 1
        assert report.gap_count == 0

    def test_gap_no_permission_in_template(self):
        routes = [RouteInfo("sales.create", "create", True, ["manage_sales"])]
        templates = [TemplateLink("sales.create", "", False, [])]
        report = PermissionMatcher().match(routes, templates)
        assert report.safe_count == 0
        assert report.gap_count == 1
        assert report.gaps[0].category == "GAP"
        assert report.gaps[0].severity == "high"

    def test_hidden_route_no_template_link(self):
        routes = [RouteInfo("api.secret", "secret", True, ["admin"])]
        templates = []
        report = PermissionMatcher().match(routes, templates)
        assert report.hidden_count == 1

    def test_unauth_template_with_login_check(self):
        routes = [RouteInfo("public.landing", "landing")]
        templates = [TemplateLink("public.landing", "", True, [])]
        report = PermissionMatcher().match(routes, templates)
        assert report.unauth_count == 1

    def test_template_guard_inheritance(self):
        routes = [
            RouteInfo(
                "cheques.index", "index", True, ["manage_payments"],
                rendered_templates=["cheques/index.html"],
            ),
            RouteInfo(
                "cheques.create", "create", True, ["manage_payments"],
            ),
        ]
        templates = [TemplateLink("cheques.create", "", False, [], file_path="templates/cheques/index.html")]
        tg = {"cheques/index.html": {"login_required", "manage_payments"}}
        tec = {"cheques/index.html": 1}
        report = PermissionMatcher().match(routes, templates, tg, tec)
        assert report.safe_count == 1
        assert report.gap_count == 0

    def test_template_guard_not_covering(self):
        routes = [
            RouteInfo(
                "cheques.index", "index", True, ["manage_payments"],
                rendered_templates=["cheques/index.html"],
            ),
            RouteInfo(
                "owner.dashboard", "dashboard", False, [],
                decorator_types={"owner_required"},
            ),
        ]
        templates = [TemplateLink("owner.dashboard", "", False, [], file_path="templates/cheques/index.html")]
        tg = {"cheques/index.html": {"login_required", "manage_payments"}}
        tec = {"cheques/index.html": 1}
        report = PermissionMatcher().match(routes, templates, tg, tec)
        assert report.safe_count == 0
        assert report.gap_count == 1

    def test_template_guard_high_endpoint_count_ignored(self):
        routes = [
            RouteInfo("sales.index", "index", True, ["manage_sales"], rendered_templates=["base.html"]),
            RouteInfo("sales.create", "create", True, ["manage_sales"]),
        ]
        templates = [TemplateLink("sales.create", "", False, [], file_path="templates/base.html")]
        tg = {"base.html": {"login_required", "manage_sales", "view_reports"}}
        tec = {"base.html": 500}
        report = PermissionMatcher().match(routes, templates, tg, tec)
        assert report.safe_count == 0
        assert report.gap_count == 1


class TestAuditReporter:
    def test_no_gaps(self):
        report = AuditReport(safe_count=5, gap_count=0)
        md = AuditReporter().to_markdown(report)
        assert "No gaps detected" in md

    def test_gap_reporting(self):
        report = AuditReport(
            safe_count=0,
            gap_count=1,
            gaps=[Gap("sales.create", "GAP", ["manage_sales"], ["none"], "high", "t.html", 1)],
        )
        md = AuditReporter().to_markdown(report)
        assert "HIGH Severity" in md
        assert "sales.create" in md


class TestIntegration:
    def test_run_audit_end_to_end(self, tmp_path):
        routes_dir = tmp_path / "routes"
        routes_dir.mkdir()
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        rf = routes_dir / "sales.py"
        rf.write_text(
            "from flask import Blueprint, render_template\n"
            "bp = Blueprint('sales', __name__)\n"
            "@bp.route('/')\n"
            "@login_required\n"
            "@permission_required('manage_sales')\n"
            "def index():\n"
            "    return render_template('sales/index.html')\n"
            "@bp.route('/create')\n"
            "@login_required\n"
            "@permission_required('manage_sales')\n"
            "def create():\n"
            "    return render_template('sales/create.html')\n"
        )
        tf = templates_dir / "sales"
        tf.mkdir()
        (tf / "index.html").write_text(
            "{% if current_user.has_permission('manage_sales') %}"
            '<a href="{{ url_for(\'sales.create\') }}">New</a>'
            "{% endif %}"
        )
        (tf / "create.html").write_text("<h1>Create</h1>")
        out = tmp_path / "report.md"
        report = run_audit(str(routes_dir), str(templates_dir), str(out))
        assert out.exists()
        assert report.safe_count > 0
