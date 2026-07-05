import os
import re

OWNER_DIR = r'D:\Data\karaj\UAE\Azad-UAE\templates\owner'

# Pattern: <p class="text-muted..."><i class="fas fa-info-circle..."></i> TEXT </p>
# Remove these redundant info paragraphs
pattern = re.compile(
    r'<p class="text-muted[^"]*">\s*<i class="fas fa-info-circle[^"]*"></i>\s*[^<]*</p>\s*',
    re.MULTILINE | re.IGNORECASE
)

# Also: <small class="form-text text-muted">\s*<i class="fas fa-info-circle..."></i> TEXT </small>
pattern2 = re.compile(
    r'<small class="form-text text-muted">\s*<i class="fas fa-info-circle[^"]*"></i>\s*[^<]*</small>\s*',
    re.MULTILINE | re.IGNORECASE
)

# Also: <p class="text-muted mb-0 mt-1">\s*<i class="fas fa-info-circle..."></i> TEXT </p>
pattern3 = re.compile(
    r'<p class="text-muted[^"]*">\s*<i class="fas fa-info-circle[^"]*"></i>\s*[^<]+</p>\s*',
    re.MULTILINE | re.IGNORECASE
)

removed_total = 0
files_modified = 0

for filename in sorted(os.listdir(OWNER_DIR)):
    if not filename.endswith('.html'):
        continue
    path = os.path.join(OWNER_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    content = pattern.sub('', content)
    content = pattern2.sub('', content)
    content = pattern3.sub('', content)

    if content != original:
        removed = original.count('fa-info-circle') - content.count('fa-info-circle')
        if removed > 0:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            files_modified += 1
            removed_total += removed
            print(f"  {filename}: removed {removed} info paragraph(s)")

print(f"\nTotal: removed {removed_total} info paragraphs from {files_modified} files")
