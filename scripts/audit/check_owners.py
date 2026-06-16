"""Check which owner users have null tenant_id."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
os.environ['SKIP_SYSTEM_INTEGRITY'] = '1'
os.environ['DISABLE_TELEMETRY'] = '1'

from app import create_app
from extensions import db
from models.user import User
from utils.tenanting import without_tenant_scope

app = create_app()
with app.app_context():
    with without_tenant_scope():
        users = User.query.filter(User.is_owner == True).all()
        for u in users:
            role_slug = u.role.slug if u.role else '?'
            print(f'  id={u.id} username={u.username} tenant_id={u.tenant_id} role={role_slug}')
        
        print(f'\nTotal owner users: {len(users)}')
        
        # Find ones that pass is_global_owner_user check
        from utils.auth_helpers import is_global_owner_user
        valid = [u for u in users if is_global_owner_user(u)]
        print(f'Valid global owners (tenant_id is None): {len(valid)}')
        for u in valid:
            print(f'  -> {u.username} (id={u.id})')
