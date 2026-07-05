path = r'D:\Data\karaj\UAE\Azad-UAE\models\invoice_settings.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = '''            from models.tenant import Tenant
            tenant = db.session.get(Tenant, tid)
            settings = InvoiceSettings(is_active=True, tenant_id=tid)
            InvoiceSettings._seed_from_tenant(settings, tenant)
            db.session.add(settings)
            db.session.commit()
            return settings'''

new = '''            from models.tenant import Tenant
            tenant = db.session.get(Tenant, tid)
            if tenant is None:
                return InvoiceSettings.query.filter_by(is_active=True).filter(
                    InvoiceSettings.tenant_id.is_(None)
                ).first()
            settings = InvoiceSettings(is_active=True, tenant_id=tid)
            InvoiceSettings._seed_from_tenant(settings, tenant)
            db.session.add(settings)
            db.session.commit()
            return settings'''

if old in content:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed invoice_settings get_active")
else:
    print("Pattern not found")
