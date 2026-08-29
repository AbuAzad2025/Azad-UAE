with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the print_settings function and add route decorator
for i, line in enumerate(lines):
    if 'def print_settings():' in line:
        lines.insert(i, '@printing_bp.route("/settings", methods=["GET", "POST"])\n')
        break

with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Added route decorator for print_settings')