with open('tests/vitest/app_global_enhanced.test.js', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with "$.fn = {};" and keep only that line, removing everything after it
# until we reach the next valid line that starts with "  $.fn.DataTable" or similar
result = []
i = 0
while i < len(lines):
    line = lines[i]
    result.append(line)
    if line.strip() == '$.fn = {};':
        # Skip all subsequent garbage lines that look like parts of the $ function
        i += 1
        while i < len(lines):
            next_line = lines[i]
            # Stop when we hit a line that starts with $.fn. or $.ajax etc.
            if next_line.strip().startswith('$.fn.') or next_line.strip().startswith('$.ajax') or next_line.strip().startswith('$.get') or next_line.strip().startswith('$.notify') or next_line.strip().startswith('$.each') or next_line.strip().startswith('$.extend'):
                result.append(next_line)
                i += 1
                break
            i += 1
        continue
    i += 1

with open('tests/vitest/app_global_enhanced.test.js', 'w', encoding='utf-8') as f:
    f.writelines(result)

print("Done")
