"""Check all templates for Jinja2 nesting errors using AST parsing."""
import os
import sys
from jinja2 import Environment, FileSystemLoader, meta


def check_file(path: str, env) -> list:
    errors = []
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()
    try:
        env.parse(source)
    except Exception as e:
        errors.append(str(e))
    return errors


def main():
    env = Environment(loader=FileSystemLoader('templates'))
    total = 0
    bad = 0
    for r, _, fs in os.walk('templates'):
        for f in fs:
            if not f.endswith('.html'):
                continue
            p = os.path.join(r, f)
            total += 1
            errs = check_file(p, env)
            if errs:
                bad += 1
                rel = os.path.relpath(p, 'templates')
                print(f'FAIL {rel}:')
                for e in errs:
                    print(f'  {e}')
    print(f'Checked {total} templates. {bad} with nesting errors.')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
