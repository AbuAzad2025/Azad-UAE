with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# The function print_settings starts at line 349 (index 348)
# Lines 353-368 (indices 352-367) need to be indented by 4 more spaces
# because the if block should be inside the function

for i in range(352, 368):  # lines 353-368 (0-indexed 352-367)
    if lines[i].strip():  # only non-empty lines
        if not lines[i].startswith(' ' * 4):
            lines[i] = '    ' + lines[i].lstrip()
            print(f'Fixed line {i+1}')

# Also fix the empty line at 352 (index 351) - should have no indent
if lines[351].strip() == '' and len(lines[351]) > 0:
    lines[351] = '\n'
    print('Fixed empty line at 353')

with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Done')