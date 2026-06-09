"""Check migration integrity."""
import os, re
from pathlib import Path

dir = Path('migrations/versions')
files = [f for f in dir.glob('*.py') if f.name != '__pycache__']

revs = {}
for f in files:
    content = f.read_text(encoding='utf-8')
    m = re.search(r"\brevision\s*=\s*['\"]([a-z0-9_]+)['\"]", content)
    if m:
        revs.setdefault(m.group(1), []).append(f.name)

dups = {k: v for k, v in revs.items() if len(v) > 1}
print(f"Total migrations: {len(files)}")
print(f"Unique revisions: {len(revs)}")
if dups:
    print("DUPLICATE revision IDs:", dups)
else:
    print("No duplicate revision IDs.")

# Check down_revision chains
for f in files:
    content = f.read_text(encoding='utf-8')
    rev = re.search(r"\brevision\s*=\s*['\"]([a-z0-9_]+)['\"]", content)
    down = re.search(r"\bdown_revision\s*=\s*\(?['\"]([a-z0-9_]+)['\"]", content)
    if rev and not down:
        print(f"HEAD (no down_revision): {f.name} rev={rev.group(1)}")
