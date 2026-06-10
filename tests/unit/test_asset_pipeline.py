import os

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_build_script_exists():
    assert os.path.isfile(os.path.join(BASE, 'scripts', 'build_assets.py'))

def test_build_function_exists():
    import scripts.build_assets
    assert hasattr(scripts.build_assets, 'build_all')
