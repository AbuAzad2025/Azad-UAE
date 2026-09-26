"""Structural debt inventory: test-module proliferation and monoliths."""

from __future__ import annotations

import collections
import pathlib
import re

ROOT = pathlib.Path(r"D:\recovers\data\karaj\azad-uae")

SUFFIX = re.compile(r"(_cov\d*|_cov\d+_\d+|_100|_99|_\d+|_extra|_gap\d*|_fuzz\d*|_more|_new|_old|_v\d+)$", re.I)

print("=" * 78)
print("TEST MODULE PROLIFERATION (files that look like coverage-chasing splits)")
print("=" * 78)
groups: dict[str, list[str]] = collections.defaultdict(list)
for f in (ROOT / "tests").rglob("test_*.py"):
    stem = f.stem
    base = SUFFIX.sub("", stem)
    if base != stem:
        groups[base].append(f.name)

multi = {k: v for k, v in groups.items() if len(v) > 1}
total_split = sum(len(v) for v in multi.values())
print(f"base modules split into suffixed variants : {len(multi)}")
print(f"files involved                             : {total_split}")
for k, v in sorted(multi.items(), key=lambda kv: -len(kv[1]))[:15]:
    print(f"  {k}: {len(v)} -> {sorted(v)[:5]}")

print()
print("=" * 78)
print("LARGEST SOURCE FILES (maintainability debt)")
print("=" * 78)
big: list[tuple[int, str]] = []
for base in ("utils", "services", "routes", "models", "ai_knowledge", "scripts", "tests"):
    for f in (ROOT / base).rglob("*.py"):
        try:
            n = sum(1 for _ in f.open(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        big.append((n, f.relative_to(ROOT).as_posix()))
big.sort(reverse=True)
print("top 15 python files by line count:")
for n, p in big[:15]:
    print(f"  {n:6d}  {p}")
print(f"files over 2000 lines: {sum(1 for n, _ in big if n > 2000)}")
print(f"files over 3000 lines: {sum(1 for n, _ in big if n > 3000)}")

print()
print("=" * 78)
print("LARGEST TEMPLATES")
print("=" * 78)
tpl = sorted(
    (
        (sum(1 for _ in f.open(encoding="utf-8", errors="replace")), f.name)
        for f in (ROOT / "templates").rglob("*.html")
    ),
    reverse=True,
)
for n, p in tpl[:8]:
    print(f"  {n:6d}  {p}")
print(f"templates over 1500 lines: {sum(1 for n, _ in tpl if n > 1500)}")
