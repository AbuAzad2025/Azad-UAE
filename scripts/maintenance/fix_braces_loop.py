import os

OWNER_DIR = r'D:\Data\karaj\UAE\Azad-UAE\templates\owner'

fixed_files = 0

for filename in sorted(os.listdir(OWNER_DIR)):
    if not filename.endswith('.html'):
        continue
    path = os.path.join(OWNER_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content
    # Loop until no more triple braces
    while '{{{' in content or '}}}' in content:
        content = content.replace('{{{', '{{')
        content = content.replace('}}}', '}}')
        content = content.replace('{{{{', '{{')
        content = content.replace('}}}}', '}}')

    if content != original:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        fixed_files += 1

print(f"Fixed braces in {fixed_files} files")
