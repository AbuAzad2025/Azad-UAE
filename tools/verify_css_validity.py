"""Parse <style> blocks with tinycss2 to detect malformed CSS in templates."""
import os
import re
import sys

try:
    import tinycss2
except ImportError:
    print('tinycss2 not installed; pip install tinycss2')
    sys.exit(0)

STYLE_BLOCK_RE = re.compile(r'<style[^>]*>(.*?)</style>', re.DOTALL | re.IGNORECASE)


def main():
    total = 0
    bad = 0
    for r, _, fs in os.walk('templates'):
        for f in fs:
            if not f.endswith('.html'):
                continue
            p = os.path.join(r, f)
            with open(p, 'r', encoding='utf-8') as fh:
                content = fh.read()
            for m in STYLE_BLOCK_RE.finditer(content):
                css = m.group(1)
                sheet = tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)
                errs = [t for t in sheet if t.type == 'error']
                if errs:
                    bad += 1
                    for e in errs:
                        print(f'CSS ERR in {os.path.relpath(p, "templates")} line {e.line}: {e.message}')
            total += 1
    print(f'Checked {total} templates. CSS errors in {bad} files.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
