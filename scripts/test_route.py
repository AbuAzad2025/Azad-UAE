import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, project_root)


def main():
    from flask import Flask
    from flask_babel import Babel

    from config import Config
    from extensions import db
    from routes.reports import reports_bp

    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    babel = Babel()
    babel.init_app(app, locale_selector=lambda: 'ar')
    app.register_blueprint(reports_bp)

    with app.test_request_context():
        for rule in app.url_map.iter_rules():
            if 'inventory' in rule.rule:
                print(f'  {rule.endpoint}: {rule.rule}')

    client = app.test_client()
    resp = client.get('/reports/inventory-reconciliation/export?format=csv&warehouse_id=1&branch_id=1')
    print(f'Status: {resp.status_code}')
    print(f'Response: {resp.data[:200]}')


if __name__ == "__main__":
    main()