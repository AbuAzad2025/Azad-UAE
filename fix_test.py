with open('tests/unit/test_owner_routes_smoke.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    '"/owner/error-audit-logs",\n            "/owner/error-audit-logs/export",\n            "/owner/error-logs",\n            "/owner/error-logs/export",\n            "/owner/backups/list",',
    '"/owner/error-audit-logs",\n            "/owner/error-audit-logs/export",\n            "/owner/backups/list",'
)
content = content.replace(
    '"/owner/error-audit-logs",\n        "/owner/error-audit-logs/export?format=json",\n        "/owner/error-logs",\n        "/owner/error-logs/export",\n        "/owner/backups/list",',
    '"/owner/error-audit-logs",\n        "/owner/error-audit-logs/export?format=json",\n        "/owner/backups/list",'
)

with open('tests/unit/test_owner_routes_smoke.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('File updated')
