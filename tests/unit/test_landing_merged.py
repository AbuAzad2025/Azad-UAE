import os
import pytest
import glob


def test_landing_en_deleted():
    assert not os.path.exists('templates/public/landing_en.html')


def test_landing_bilingual():
    path = 'templates/public/landing.html'
    assert os.path.exists(path)
    with open(path, encoding='utf-8') as f:
        content = f.read()
    assert 'current_language' in content


def test_routes_no_landing_en():
    for fpath in glob.glob('routes/*.py'):
        with open(fpath, encoding='utf-8') as f:
            for lineno, line in enumerate(f, 1):
                if 'landing_en' in line:
                    pytest.fail(f'{fpath}:{lineno} still references landing_en')
