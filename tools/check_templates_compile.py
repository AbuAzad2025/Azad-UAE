"""Smoke test: ensure every Jinja2 template still compiles (parses) after edits.

This does NOT render (no context needed) -- it catches syntax/structural breakage
introduced by automated edits like CSS externalization (D6).
"""
import os
import sys
from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError


def main(templates_dir):
    env = Environment(loader=FileSystemLoader(templates_dir))
    total = 0
    failed = []
    for root, _, files in os.walk(templates_dir):
        for fname in files:
            if not fname.endswith('.html'):
                continue
            rel = os.path.relpath(os.path.join(root, fname), templates_dir).replace('\\', '/')
            total += 1
            try:
                source = env.loader.get_source(env, rel)[0]
                env.parse(source)
            except TemplateSyntaxError as e:
                failed.append((rel, f'line {e.lineno}: {e.message}'))
            except Exception as e:  # noqa: BLE001
                failed.append((rel, str(e)))

    print(f'Templates checked: {total}')
    print(f'Compile failures:  {len(failed)}')
    for rel, msg in failed:
        print(f'  FAIL {rel} -> {msg}')
    return 1 if failed else 0


if __name__ == '__main__':
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main(os.path.join(root, 'templates')))
