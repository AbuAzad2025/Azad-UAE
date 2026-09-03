"""Detect replaced/broken text in source files (NOT in legitimate i18n / binary / cache).

Scans for:
  - U+FFFD (replacement char) — almost always a mojibake/broken-decode signal
  - Single-char placeholders: ?, ?, ?, ?, etc., IN a text/comment context where
    Arabic should be present (i.e. inside a string with Arabic neighbors it's
    expected; but a lone "?" or "□" mid-line outside string declarations means
    encoding dropped the byte).

Output: list of files + lines + a 50-char preview, with CLEAN categories
(AdminLTE i18n, fonts, images, encrypted backups, ruff cache, ai_knowledge
  knowledge base, etc.) excluded.
"""
import pathlib, re, sys, json

ROOT = pathlib.Path(r"D:\recovers\data\karaj\azad-uae")

# Categories EXCLUDED entirely (legitimate / unrelated)
EXCLUDE_PATH = [
    ".git", ".venv", "venv", "node_modules", "dist", "build",
    ".ruff_cache", ".mypy_cache", ".pytest_cache", "__pycache__",
    "instance/backups", "static/adminlte/plugins/select2/js/i18n",
    "static/fonts", "static/assets", "static/img", "static/img-dist",
    "ai_knowledge/knowledge_base.py",
    "ai_knowledge/memory", "ai_knowledge/datasets",
    "migrations/versions",  # generated; any noise = upstream
]

SOURCE_SUFFIX = {".py", ".js", ".ts", ".html", ".jinja", ".jinja2", ".css",
                  ".md", ".rst", ".txt", ".json", ".yaml", ".yml",
                  ".csv", ".po", ".mo", ".toml", ".ini", ".cfg", ".sh"}
SKIP_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
               ".woff", ".woff2", ".ttf", ".eot", ".otf", ".ico",
               ".pdf", ".gz", ".zip", ".tar", ".enc", ".db", ".sqlite",
               ".png.base64", ".svg"}

REPLACEMENT = "\ufffd"  # U+FFFD
EXTRA = re.compile(r"[\ufffa-\uffff]")


def is_probably_text(path: pathlib.Path) -> bool:
    if path.is_dir():
        return False
    if path.suffix.lower() in SKIP_SUFFIX:
        return False
    return True


def should_skip(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    return any(rel.startswith(p.replace("\\", "/")) or f"/{p}/" in "/" + rel for p in EXCLUDE_PATH)


def main() -> int:
    findings = []
    for p in ROOT.rglob("*"):
        if not is_probably_text(p):
            continue
        rel = str(p.relative_to(ROOT))
        if should_skip(rel):
            continue
        if p.suffix.lower() not in SOURCE_SUFFIX and p.name not in {"Dockerfile", "Procfile"}:
            continue
        try:
            raw = p.read_bytes()
        except Exception:
            continue
        # skip NUL-byte files (binary)
        if b"\x00" in raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("cp1252", errors="replace")
            except Exception:
                continue
        for i, line in enumerate(text.splitlines(), 1):
            hit = False
            for marker in (REPLACEMENT,):
                if marker in line:
                    findings.append((rel, i, line.strip()[:120], "U+FFFD"))
                    hit = True
                    break
            if not hit and EXTRA.search(line):
                findings.append((rel, i, line.strip()[:120], "extra"))
            if len(findings) >= 400:
                break
        if len(findings) >= 400:
            break

    by_file = {}
    for rel, lineno, snippet, marker in findings:
        by_file.setdefault(rel, []).append((lineno, snippet, marker))

    lines = [f"Replacement/box-glyph findings: {len(findings)}",
             f"Files: {len(by_file)}", ""]
    for rel in sorted(by_file):
        lines.append(f"-- {rel} --")
        for lineno, snippet, marker in by_file[rel][:50]:
            lines.append(f"   L{lineno} [{marker}]: {snippet}")
    out = "\n".join(lines)
    out_path = r"C:\Users\azad1\AppData\Local\Temp\opencode\nonascii_report.txt"
    pathlib.Path(out_path).write_text(out, encoding="utf-8")
    print(f"Findings: {len(findings)} | Files: {len(by_file)} | Report: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())