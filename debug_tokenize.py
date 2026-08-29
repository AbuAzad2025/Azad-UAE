import tokenize
import io

with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'rb') as f:
    content = f.read()

# Tokenize to see what Python's parser sees
try:
    tokens = list(tokenize.tokenize(io.BytesIO(content).readline))
    print("Tokenization successful - no syntax errors")
except tokenize.TokenError as e:
    print("TokenError:", e)
except IndentationError as e:
    print("IndentationError:", e)
    print("Error at line:", e.lineno, "offset:", e.offset)
except Exception as e:
    print("Error:", type(e).__name__, e)

# Also check line 368 specifically
with open(r'D:\recovers\data\karaj\azad-uae\routes\printing.py', 'rb') as f:
    content = f.read()
lines = content.splitlines()
print(f"Total lines: {len(lines)}")
print(f"Line 367 (idx 366): len={len(lines[366])}, indent={len(lines[366]) - len(lines[366].lstrip())}, content={repr(lines[366][:80])}")
print(f"Line 368 (idx 367): indent={len(lines[367]) - len(lines[367].lstrip())}, starts_4={lines[367].startswith(b'    ')}")