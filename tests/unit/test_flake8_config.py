import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestFlake8Config:
    def test_flake8_config_file_exists(self):
        assert (PROJECT_ROOT / ".flake8").exists()

    def test_flake8_runs_without_errors_on_clean_files(self):
        clean_files = [
            "config.py",
            "utils/bootstrap_keys.py",
            "tests/unit/test_bootstrap_keys.py",
        ]
        result = subprocess.run(
            [sys.executable, "-m", "flake8"] + clean_files,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"flake8 failed: {result.stdout}{result.stderr}"

    def test_flake8_ignores_user_style_rules(self):
        config_path = PROJECT_ROOT / ".flake8"
        content = config_path.read_text(encoding="utf-8")
        assert "E301" in content
        assert "E302" in content
        assert "E704" in content

    def test_flake8_max_line_length_120(self):
        config_path = PROJECT_ROOT / ".flake8"
        content = config_path.read_text(encoding="utf-8")
        assert "max-line-length = 120" in content
