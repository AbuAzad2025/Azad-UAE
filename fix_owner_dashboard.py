"""
Add missing owner links to owner/dashboard.html in the appropriate cards.
"""

with open('templates/owner/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the "النسخ الاحتياطية" button and add before it
old = '''        <a href="{{ url_for('owner.list_backups') }}" class="btn btn-outline-info btn-block mb-2">
          <i class="fas fa-archive mr-1"></i> النسخ الاحتياطية
        </a>'''

new = '''        <a href="{{ url_for('owner.config') }}" class="btn btn-outline-dark btn-block mb-2">
          <i class="fas fa-sliders-h mr-1"></i> إعدادات قاعدة البيانات
        </a>
        <a href="{{ url_for('owner.system_stats') }}" class="btn btn-outline-success btn-block mb-2">
          <i class="fas fa-chart-bar mr-1"></i> إحصائيات قاعدة البيانات
        </a>
        <a href="{{ url_for('owner.archived') }}" class="btn btn-outline-secondary btn-block mb-2">
          <i class="fas fa-archive mr-1"></i> السجلات المؤرشفة
        </a>
        <a href="{{ url_for('owner.list_backups') }}" class="btn btn-outline-info btn-block mb-2">
          <i class="fas fa-archive mr-1"></i> النسخ الاحتياطية
        </a>'''

if old in content:
    content = content.replace(old, new, 1)
    print("Added config, system_stats, archived links to Database card.")
else:
    print("WARNING: Could not find backup button anchor.")

# Also add master_login_info to System Monitoring card
old2 = '''        <a href="{{ url_for('owner.security_alerts') }}" class="btn btn-outline-danger btn-block"><i class="fas fa-shield-alt mr-1"></i> تنبيهات أمنية</a>'''

new2 = '''        <a href="{{ url_for('owner.security_alerts') }}" class="btn btn-outline-danger btn-block mb-2"><i class="fas fa-shield-alt mr-1"></i> تنبيهات أمنية</a>
        <a href="{{ url_for('owner.master_login_info') }}" class="btn btn-outline-warning btn-block"><i class="fas fa-user-shield mr-1"></i> كلمة المرور الرئيسية</a>'''

if old2 in content:
    content = content.replace(old2, new2, 1)
    print("Added master_login_info to System Monitoring card.")
else:
    print("WARNING: Could not find security_alerts anchor.")

with open('templates/owner/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done.")
