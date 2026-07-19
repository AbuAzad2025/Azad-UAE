import os


def _import_bp(app, module_path, var_name):
    try:
        mod = __import__(module_path, fromlist=[var_name])
        return getattr(mod, var_name)
    except Exception as exc:
        import sys
        import traceback

        sys.stderr.write(
            f"[SYSTEM_INIT_ERROR] Failed to import blueprint {module_path}.{var_name}: {exc}\n"
        )
        traceback.print_exc()
        try:
            from services.logging_core import LoggingCore

            with app.app_context():
                LoggingCore.log_error(
                    message=str(exc),
                    category="SYSTEM_INIT",
                    source=f"bootstrap.blueprints._import_bp({module_path})",
                    level="ERROR",
                    exception=exc,
                )
        except Exception as log_exc:
            sys.stderr.write(f"[SYSTEM_INIT_ERROR] Failed to log to DB: {log_exc}\n")
        raise


def _make_ai_fallback(ai_import_error):
    from flask import Blueprint, flash, redirect, url_for
    from flask_login import login_required

    ai_bp = Blueprint("ai", __name__, url_prefix="/ai")

    @ai_bp.route("/assistant")
    @login_required
    def assistant_page():
        flash(
            f"AI Module failed to load on server start. Please check logs. Error: {ai_import_error}",
            "error",
        )
        return redirect(url_for("main.dashboard"))

    @ai_bp.route("/config")
    @login_required
    def config():
        flash(
            f"AI Module failed to load on server start. Please check logs. Error: {ai_import_error}",
            "error",
        )
        return redirect(url_for("main.dashboard"))

    @ai_bp.route("/chat", methods=["POST"])
    def chat():
        return {"error": "AI Module Unavailable"}, 503

    @ai_bp.route("/recommend-price", methods=["POST"])
    def recommend_price():
        return {"error": "AI Module Unavailable"}, 503

    @ai_bp.route("/check-stock", methods=["POST"])
    def check_stock():
        return {"error": "AI Module Unavailable"}, 503

    @ai_bp.route("/analyze-customer/<int:customer_id>", methods=["GET"])
    def analyze_customer(customer_id):
        return {"error": "AI Module Unavailable"}, 503

    @ai_bp.route("/exchange-rate/<currency>", methods=["GET"])
    def exchange_rate(currency):
        return {"error": "AI Module Unavailable"}, 503

    @ai_bp.route("/search-market-price/<int:product_id>", methods=["GET"])
    def search_market_price(product_id):
        return {"error": "AI Module Unavailable"}, 503

    @ai_bp.route("/find-compatible/<int:product_id>", methods=["GET"])
    def find_compatible(product_id):
        return {"error": "AI Module Unavailable"}, 503

    @ai_bp.route("/upload-excel", methods=["POST"])
    def upload_excel():
        return {"error": "AI Module Unavailable"}, 503

    @ai_bp.route("/<path:path>")
    def catch_all(path):
        try:
            from flask import session

            if not session.get("ai_unavailable_notified"):
                flash(
                    "المساعد الذكي غير متاح حالياً بسبب إعدادات غير مكتملة.", "warning"
                )
                session["ai_unavailable_notified"] = True
        except Exception as e:
            import sys
            import traceback

            sys.stderr.write(
                f"[AI_FALLBACK_WARNING] Failed to set session notification: {e}\n"
            )
            traceback.print_exc()
            try:
                from services.logging_core import LoggingCore

                LoggingCore.log_error(
                    message=str(e),
                    category="SYSTEM_INIT",
                    source="bootstrap.blueprints.ai_fallback.catch_all",
                    level="ERROR",
                    exception=e,
                )
            except Exception:
                import logging

                logging.getLogger(__name__).exception(
                    "AI fallback catch-all route — LoggingCore.log_error itself failed"
                )
        return redirect(url_for("main.dashboard"))

    return ai_bp


def register_blueprints(app):
    auth_bp = _import_bp(app, "routes.auth", "auth_bp")
    main_bp = _import_bp(app, "routes.main", "main_bp")
    sales_bp = _import_bp(app, "routes.sales", "sales_bp")
    products_bp = _import_bp(app, "routes.products", "products_bp")
    customers_bp = _import_bp(app, "routes.customers", "customers_bp")
    reports_bp = _import_bp(app, "routes.reports", "reports_bp")
    treasury_bp = _import_bp(app, "routes.treasury", "treasury_bp")
    api_bp = _import_bp(app, "routes.api", "api_bp")
    api_enhanced_bp = _import_bp(app, "routes.api_enhanced", "api_enhanced_bp")
    suppliers_bp = _import_bp(app, "routes.suppliers", "suppliers_bp")
    purchases_bp = _import_bp(app, "routes.purchases", "purchases_bp")
    expenses_bp = _import_bp(app, "routes.expenses", "expenses_bp")
    ledger_bp = _import_bp(app, "routes.ledger", "ledger_bp")
    owner_bp = _import_bp(app, "routes.owner", "owner_bp")
    owner_admin_bp = _import_bp(app, "routes.owner_admin", "owner_admin_bp")
    payments_bp = _import_bp(app, "routes.payments", "payments_bp")
    warehouse_bp = _import_bp(app, "routes.warehouse", "warehouse_bp")
    uinv_bp = _import_bp(app, "routes.unified_inventory", "uinv_bp")
    language_bp = _import_bp(app, "routes.language", "language_bp")
    tenants_bp = _import_bp(app, "routes.tenants", "tenants_bp")
    payroll_bp = _import_bp(app, "routes.payroll", "payroll_bp")

    if os.environ.get("DISABLE_AI"):
        ai_bp = _make_ai_fallback("AI disabled by server configuration")
    else:
        try:
            from routes.ai_routes import ai_bp
        except Exception as e:
            ai_import_error = str(e)
            import traceback

            traceback.print_exc()
            ai_bp = _make_ai_fallback(ai_import_error)

    users_bp = _import_bp(app, "routes.users", "users_bp")
    branches_bp = _import_bp(app, "routes.branches", "branches_bp")
    partners_bp = _import_bp(app, "routes.partners", "partners_bp")
    pos_bp = _import_bp(app, "routes.pos", "pos_bp")
    returns_bp = _import_bp(app, "routes.returns", "returns_bp")
    cheques_bp = _import_bp(app, "routes.cheques", "cheques_bp")
    advanced_ledger_bp = _import_bp(app, "routes.advanced_ledger", "advanced_ledger_bp")
    admin_ledger_bp = _import_bp(app, "routes.admin_ledger", "admin_ledger_bp")
    store_bp = _import_bp(app, "routes.store", "store_bp")
    shop_bp = _import_bp(app, "routes.shop", "shop_bp")
    payment_vault_bp = _import_bp(app, "routes.payment_vault", "payment_vault_bp")
    whatsapp_bp = _import_bp(app, "routes.whatsapp", "whatsapp_bp")
    monitoring_bp = _import_bp(app, "routes.monitoring", "monitoring_bp")
    public_bp = _import_bp(app, "routes.public", "public_bp")
    api_analytics_bp = _import_bp(app, "routes.api_analytics", "api_analytics_bp")
    api_docs_bp = _import_bp(app, "routes.api_docs", "api_docs_bp")
    graphql_bp = _import_bp(app, "routes.graphql", "graphql_bp")
    gamification_bp = _import_bp(app, "routes.gamification", "gamification_bp")
    crm_bp = _import_bp(app, "routes.crm", "crm_bp")
    tickets_bp = _import_bp(app, "routes.tickets", "tickets_bp")
    projects_bp = _import_bp(app, "routes.projects", "projects_bp")
    hr_bp = _import_bp(app, "routes.hr", "hr_bp")
    email_marketing_bp = _import_bp(app, "routes.email_marketing", "email_marketing_bp")
    printing_bp = _import_bp(app, "routes.printing", "printing_bp")
    billing_webhook_bp = _import_bp(
        app, "routes.billing_webhooks", "billing_webhook_bp"
    )

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(pos_bp)
    app.register_blueprint(returns_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(partners_bp)
    app.register_blueprint(suppliers_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(warehouse_bp)
    app.register_blueprint(uinv_bp)
    app.register_blueprint(branches_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(cheques_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(payment_vault_bp)
    app.register_blueprint(ledger_bp)
    app.register_blueprint(advanced_ledger_bp)
    app.register_blueprint(admin_ledger_bp)
    app.register_blueprint(payroll_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(treasury_bp)
    app.register_blueprint(api_analytics_bp)
    app.register_blueprint(gamification_bp)
    app.register_blueprint(monitoring_bp)
    app.register_blueprint(store_bp)
    app.register_blueprint(shop_bp)
    app.register_blueprint(tenants_bp)
    app.register_blueprint(language_bp)
    app.register_blueprint(whatsapp_bp)
    app.register_blueprint(api_docs_bp)
    app.register_blueprint(ai_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(api_enhanced_bp)
    app.register_blueprint(graphql_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(owner_bp)
    app.register_blueprint(owner_admin_bp)
    app.register_blueprint(crm_bp)
    app.register_blueprint(tickets_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(hr_bp)
    app.register_blueprint(email_marketing_bp)
    app.register_blueprint(printing_bp)
    app.register_blueprint(billing_webhook_bp)

    return app
