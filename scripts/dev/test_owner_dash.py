"""Set owner password and test dashboard."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
os.environ['SKIP_SYSTEM_INTEGRITY'] = '1'
os.environ['DISABLE_TELEMETRY'] = '1'

from app import create_app
from extensions import db
from models.user import User
from utils.tenanting import without_tenant_scope
from flask_login import login_user

app = create_app()
app.config['WTF_CSRF_ENABLED'] = False

with app.app_context():
    with without_tenant_scope():
        owner = User.query.filter_by(username='owner').first()
        if owner:
            # Check existing password
            found_pw = None
            for pw in ['change-me-strong-password', 'owner', 'Azad@2024', 'admin']:
                if owner.check_password(pw):
                    found_pw = pw
                    break
            
            if found_pw:
                print(f'Current password: {found_pw}')
            else:
                # Reset password
                new_pw = 'owner123'
                owner.set_password(new_pw)
                db.session.commit()
                print(f'Password reset to: {new_pw}')
            
            # Now test owner dashboard
            print(f'\nOwner: {owner.username}, tenant_id={owner.tenant_id}')
            from utils.auth_helpers import is_global_owner_user
            print(f'is_global_owner_user: {is_global_owner_user(owner)}')

# Test with test client
with app.test_client() as client:
    with app.app_context():
        with without_tenant_scope():
            owner = User.query.filter_by(username='owner').first()
            test_pw = found_pw or 'owner123'
    
    # Use session-based login instead of POST to avoid CSRF issues
    with client:
        with app.app_context():
            with without_tenant_scope():
                from flask_login import login_user
                with client.session_transaction() as sess:
                    sess['user_id'] = owner.id
                    sess['_fresh'] = True
        
        # Try owner dashboard
        resp = client.get('/owner/dashboard', follow_redirects=False)
        print(f'\nOwner dashboard status: {resp.status_code}')
        print(f'Location: {resp.headers.get("Location", "none")}')
        
        if resp.status_code != 200:
            # Show as much of the response as possible
            html = resp.data.decode('utf-8')
            if '<title>' in html:
                import re
                m = re.search(r'<title>(.*?)</title>', html)
                if m:
                    print(f'Title: {m.group(1)}')
            # Try to find error details
            for keyword in ['error', 'خطأ', 'Traceback', '500', 'Internal']:
                idx = html.lower().find(keyword.lower())
                if idx >= 0:
                    print(f'Found "{keyword}" at position {idx}')
                    print(html[max(0,idx-50):idx+200])
                    break
            print(f'\nFull response ({len(html)} bytes):')
            print(html[:2000])
        else:
            print('Owner dashboard returned 200 OK!')
            html = resp.data.decode('utf-8')
            import re
            m = re.search(r'<title>(.*?)</title>', html)
            if m:
                print(f'Title: {m.group(1)}')
