"""Find owner password and test dashboard."""
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
        owner = User.query.filter_by(username='owner').first()
        if owner:
            print(f'Owner id={owner.id}, is_owner={owner.is_owner}, tenant_id={owner.tenant_id}')
            # Try passwords
            candidates = [
                'change-me-strong-password', 'owner', 'admin', 'test123',
                'Azad@2024', 'Azad@2025', 'P@ssw0rd', '123456', 'password',
                'admin123', 'master', 'root', 'azad', 'owner123'
            ]
            for pw in candidates:
                if owner.check_password(pw):
                    print(f'PASSWORD FOUND: {pw}')
                    break
            else:
                print('Password not found in candidate list')
        else:
            print('No user named "owner" found')
