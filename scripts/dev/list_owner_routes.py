import re
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

with open('routes/owner.py', 'r', encoding='utf-8') as f:
    content = f.read()

routes = re.findall(r"@owner_bp\.route\('([^']+)'(?:[^\n]*methods=\[([^\]]*)\])?[^\n]*\)\n@login_required\n@(?:owner_required|company_admin_required)\ndef ([^(]+)", content)

for r in routes:
    methods = r[1].strip().replace("'", "").replace(" ", "") if r[1] else 'GET'
    print(f'{methods:20} {r[0]:50} {r[2]}')
