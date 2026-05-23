import os
import re


def _iter_files(root: str, exts):
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if any(fn.endswith(ext) for ext in exts):
                yield os.path.join(dirpath, fn)


def _norm_static_ref(ref: str):
    ref = ref.strip().strip("\"'").strip()
    ref = ref.split("?", 1)[0].split("#", 1)[0]
    if ref.startswith("/static/"):
        return ref[len("/static/") :]
    if ref.startswith("static/"):
        return ref[len("static/") :]
    return None


def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    templates_dir = os.path.join(base_dir, "templates")
    static_dir = os.path.join(base_dir, "static")

    rx_url_for = re.compile(
        r"url_for\(\s*['\"]static['\"]\s*,\s*filename\s*=\s*['\"]([^'\"]+)['\"]"
    )
    rx_attr = re.compile(
        r"""(?:src|href)\s*=\s*['"]([^'"]+)['"]""",
        re.I,
    )
    rx_css_url = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)""", re.I)

    missing = []
    referenced = 0

    scan_roots = [
        (templates_dir, (".html",)),
        (base_dir, (".py", ".json", ".js", ".css")),
    ]

    for root, exts in scan_roots:
        if not os.path.isdir(root):
            continue
        for fp in _iter_files(root, exts):
            if os.path.commonpath([fp, static_dir]) == static_dir:
                continue
            rel = os.path.relpath(fp, base_dir)
            try:
                txt = open(fp, "r", encoding="utf-8", errors="ignore").read()
            except OSError:
                continue

            for m in rx_url_for.finditer(txt):
                ref = m.group(1)
                if "{{" in ref or "{%" in ref:
                    continue
                referenced += 1
                norm = ref.split("?", 1)[0].split("#", 1)[0]
                target = os.path.join(static_dir, norm)
                if not os.path.isfile(target):
                    missing.append((rel, norm))

            for m in rx_attr.finditer(txt):
                ref = m.group(1)
                if ref.startswith(("http://", "https://", "data:")):
                    continue
                if "{{" in ref or "{%" in ref:
                    continue
                norm = _norm_static_ref(ref)
                if not norm:
                    continue
                referenced += 1
                target = os.path.join(static_dir, norm)
                if not os.path.isfile(target):
                    missing.append((rel, norm))

            for m in rx_css_url.finditer(txt):
                ref = m.group(1)
                if ref.startswith(("http://", "https://", "data:")):
                    continue
                if "{{" in ref or "{%" in ref:
                    continue
                norm = _norm_static_ref(ref)
                if not norm:
                    continue
                referenced += 1
                target = os.path.join(static_dir, norm)
                if not os.path.isfile(target):
                    missing.append((rel, norm))

    missing = sorted(set(missing))
    print("referenced", referenced)
    print("missing_count", len(missing))
    for rel, norm in missing:
        print(f"{rel}: {norm}")


if __name__ == "__main__":
    main()

