import re

# Fix tenant isolation in delete action
path = r'D:\Data\karaj\UAE\Azad-UAE\routes\owner.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_delete = """        elif action == 'delete':
            record_id = request.form.get('record_id', type=int)
            if record_id:
                rec = ExchangeRateRecord.query.get(record_id)
                if rec:
                    db.session.delete(rec)
                    db.session.commit()
                    flash('✅ تم حذف السجل.', 'success')"""

new_delete = """        elif action == 'delete':
            record_id = request.form.get('record_id', type=int)
            if record_id:
                rec = ExchangeRateRecord.query.filter_by(
                    id=record_id, tenant_id=tenant_id
                ).first()
                if rec:
                    db.session.delete(rec)
                    db.session.commit()
                    flash('✅ تم حذف السجل.', 'success')
                else:
                    flash('⚠️ السجل غير موجود أو لا يخصك.', 'warning')"""

if old_delete in content:
    content = content.replace(old_delete, new_delete)
    print("Fixed tenant isolation in delete action")
else:
    print("Delete pattern not found")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

# Add exchange rates link to owner dashboard
path2 = r'D:\Data\karaj\UAE\Azad-UAE\templates\owner\dashboard.html'
with open(path2, 'r', encoding='utf-8') as f:
    content2 = f.read()

old_link = """        <a href="{{ url_for('owner.currency_settings') }}" class="btn btn-outline-info btn-block mb-2"><i class="fas fa-dollar-sign mr-1"></i> العملات</a>"""
new_link = """        <a href="{{ url_for('owner.currency_settings') }}" class="btn btn-outline-info btn-block mb-2"><i class="fas fa-dollar-sign mr-1"></i> العملات</a>
        <a href="{{ url_for('owner.exchange_rates') }}" class="btn btn-outline-primary btn-block mb-2"><i class="fas fa-exchange-alt mr-1"></i> أسعار الصرف</a>"""

if old_link in content2:
    content2 = content2.replace(old_link, new_link)
    print("Added exchange rates link to dashboard")
else:
    print("Dashboard link pattern not found")

with open(path2, 'w', encoding='utf-8') as f:
    f.write(content2)
