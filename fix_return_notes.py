import re

with open('D:/Data/karaj/UAE/Azad-UAE/templates/sales/view.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the exact line using regex
pattern = r'(\s+<input type="text" class="form-control return-notes" id="return_notes_\{\{ line\.id \}\}" name="return_notes_\{\{ line\.id \}\}" placeholder="\{\{ t\('[^']*'\) \}\} \{\{ t\('[^']*'\) \}\}" maxlength="500">)'

match = re.search(pattern, content)
if match:
    print(f"Found: {match.group(0)[:100]}...")
    new_line = '''                    <label for="return_notes_{{ line.id }}" class="sr-only">{{ t('سبب') }} {{ t('الإرجاع') }}</label>
                    <input type="text" class="form-control return-notes" id="return_notes_{{ line.id }}" name="return_notes_{{ line.id }}" placeholder="{{ t('سبب') }} {{ t('الإرجاع') }}" maxlength="500">'''
    content = content.replace(match.group(0), new_line)
    with open('D:/Data/karaj/UAE/Azad-UAE/templates/sales/view.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Replaced successfully!')
else:
    print('Pattern not found')
    # Debug: show lines containing return_notes
    for i, line in enumerate(content.split('\n')):
        if 'return_notes' in line:
            print(f'Line {i}: {line.strip()[:80]}...')