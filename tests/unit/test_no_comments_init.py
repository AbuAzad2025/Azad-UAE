import os


MODELS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'models')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.readlines()


def test_no_comments_in_init():
    lines = _read(os.path.join(MODELS_DIR, '__init__.py'))
    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if stripped.startswith('#'):
            raise AssertionError(f"Line {i} is a comment: {line!r}")


def test_no_blank_lines_in_events():
    lines = _read(os.path.join(MODELS_DIR, 'events.py'))
    for i in range(len(lines) - 1):
        if lines[i].strip() == '' and lines[i + 1].strip() == '':
            raise AssertionError(f"Consecutive blank lines at lines {i + 1} and {i + 2}")
