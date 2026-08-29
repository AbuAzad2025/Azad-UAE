with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if i >= 360 and i < 375:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        print(f'{i+1}: indent={indent}, stripped={stripped[:50]!r}')