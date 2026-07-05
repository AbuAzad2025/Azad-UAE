import re

path = r'D:\Data\karaj\UAE\Azad-UAE\templates\owner\dashboard.html'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Patterns to remove: <p class="text-muted small mb-3"><i class="fas fa-info-circle mr-1"></i> ... </p>
pattern = re.compile(
    r'<p class="text-muted small mb-3">\s*<i class="fas fa-info-circle mr-1"></i>\s*[^<]+</p>\s*',
    re.MULTILINE
)

# Count matches
matches = pattern.findall(content)
print(f"Found {len(matches)} info paragraphs to remove")

# Remove them
content = pattern.sub('', content)

# Also shorten the top warning banner
old_banner = '''<div class="owner-warning-permanent d-flex align-items-center mb-4 ic-1">
  <i class="fas fa-shield-alt mr-3 text-danger ic-2"></i>
  <span class="ic-3">
    منطقة الإدارة العليا - جميع العمليات في هذه اللوحة مسجلة لأغراض التدقيق والأمان.
  </span>
</div>'''

new_banner = '''<div class="owner-warning-permanent d-flex align-items-center mb-4 ic-1">
  <i class="fas fa-shield-alt mr-3 text-danger ic-2"></i>
  <span class="ic-3">منطقة الإدارة العليا</span>
</div>'''

if old_banner in content:
    content = content.replace(old_banner, new_banner)
    print("Shortened top warning banner")
else:
    print("Banner pattern not found (may have changed)")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Removed {len(matches)} redundant info paragraphs")
print("Done")
