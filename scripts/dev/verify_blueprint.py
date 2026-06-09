content = open(r'D:\Data\karaj\UAE\Azad-UAE\docs\ERP_ACCOUNTING_MASTER_BLUEPRINT.md', 'r', encoding='utf-8').read()
lines = content.split('\n')
print('Total lines:', len(lines))
checks = [
    ('COMPLETE (June 9, 2026)', 'Phase 2 status'),
    ('17 rows', 'Profit center count'),
    ('Tenant.settings', 'Tenant.settings bug'),
    ('Last updated: June 9, 2026', 'Last updated date'),
]
for phrase, label in checks:
    ok = phrase in content
    print(f'  {label}: {"OK" if ok else "MISSING"}')
