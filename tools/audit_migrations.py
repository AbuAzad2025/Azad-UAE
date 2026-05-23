import os
import re


def _read_var(text: str, name: str):
    m = re.search(rf"^{name}\s*=\s*(['\"])(.*?)\1\s*$", text, flags=re.M)
    if m:
        return m.group(2)
    m2 = re.search(rf"^{name}\s*=\s*None\s*$", text, flags=re.M)
    if m2:
        return None
    return None


def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    versions_dir = os.path.join(base_dir, "migrations", "versions")
    rev_to_file = {}
    down_of = {}

    for fn in sorted(os.listdir(versions_dir)):
        if not fn.endswith(".py"):
            continue
        fp = os.path.join(versions_dir, fn)
        txt = open(fp, "r", encoding="utf-8").read()
        rev = _read_var(txt, "revision")
        if not rev:
            continue
        down = _read_var(txt, "down_revision")
        rev_to_file[rev] = fn
        down_of[rev] = down

    referenced = {d for d in down_of.values() if d}
    heads = sorted([r for r in down_of if r not in referenced])
    bases = sorted([r for r, d in down_of.items() if d is None])
    missing_down = sorted([(r, d) for r, d in down_of.items() if d and d not in rev_to_file])

    print("count", len(rev_to_file))
    print("bases", bases)
    print("heads", heads)
    print("missing_down", missing_down)

    for h in heads:
        chain = []
        cur = h
        seen = set()
        while cur and cur not in seen:
            seen.add(cur)
            chain.append(cur)
            cur = down_of.get(cur)
        print("\nhead", h, "file", rev_to_file.get(h))
        print(" -> ".join(chain))


if __name__ == "__main__":
    main()

