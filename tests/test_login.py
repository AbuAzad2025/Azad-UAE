#!/usr/bin/env python
"""Test login flow."""
import requests
import re

s = requests.Session()
r = s.get('http://localhost:5000/auth/login')
print('Login page:', r.status_code)

csrf = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
if csrf:
    print('CSRF token found')
    r = s.post('http://localhost:5000/auth/login', data={
        'username': 'demo_admin',
        'password': 'Demo@2026',
        'csrf_token': csrf.group(1)
    }, allow_redirects=False)
    print('Login:', r.status_code, r.headers.get('Location'))
    if r.status_code == 302:
        r = s.get('http://localhost:5000/')
        print('Dashboard:', r.status_code, 'Demo' in r.text)
else:
    print('No CSRF token')