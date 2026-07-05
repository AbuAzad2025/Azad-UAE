from app import create_app, db
from app.models.tenant import Tenant
app = create_app()
with app.app_context():
    tenant = Tenant.query.first()
    print(f"Connection successful, first tenant: {tenant.name if tenant else 'None'}")
