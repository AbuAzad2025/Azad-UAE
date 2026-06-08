"""Ensure JS-toggled display:none/inline/block/flex remain inline (not replaced by class)."""
import os
import re

IC_ON_TOGGLE_RE = re.compile(
    r'class="[^"]*\bic-\d+[^"]*"[^>]*style="[^"]*display\s*:\s*(none|inline|block|inline-block|flex)',
    re.IGNORECASE
)


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
            if IC_ON_TOGGLE_RE.search(content):
                bad += 1
                print(f'WARN {os.path.relpath(p, "templates")}: display toggle has .ic-N class')
            total += 1
    print(f'Checked {total} templates. JS-toggle violations: {bad}.')
    return 1 if bad else 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
