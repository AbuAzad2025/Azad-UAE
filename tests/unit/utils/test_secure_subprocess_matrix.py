"""SecureSubprocess — allowlist enforcement and happy-path execution."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from utils.secure_subprocess import (
    _PG_TOOL_BASENAMES,
    SecureSubprocess,
    _executable_basename,
)

ROOT = Path(__file__).resolve().parents[3]


class TestExecutableBasename:
    def test_windows_and_posix_separators(self):
        assert _executable_basename(r"C:\tools\pg_dump.exe") == "pg_dump.exe"
        assert _executable_basename("/usr/bin/git") == "git"

    def test_pg_tool_allowlist_contents(self):
        for name in ("pg_dump", "pg_restore", "psql", "createdb", "dropdb"):
            assert name in _PG_TOOL_BASENAMES


class TestRunAllowlist:
    def test_empty_argv_rejected(self):
        with pytest.raises(ValueError, match="argv required"):
            SecureSubprocess.run([], allowed_basenames=_PG_TOOL_BASENAMES)

    def test_non_allowlisted_executable_rejected(self):
        with pytest.raises(ValueError, match="not allowlisted"):
            SecureSubprocess.run(["definitely-not-allowed.exe"], allowed_basenames=_PG_TOOL_BASENAMES)

    def test_blank_executable_rejected(self):
        with pytest.raises(ValueError, match="empty executable"):
            SecureSubprocess.run(["   "], allowed_basenames=_PG_TOOL_BASENAMES)

    def test_runs_current_interpreter(self):
        proc = SecureSubprocess.run(
            [sys.executable, "-c", "print('secsub-ok')"],
            allowed_basenames=frozenset({os.path.basename(sys.executable)}),
        )
        assert proc.returncode == 0
        assert "secsub-ok" in proc.stdout

    def test_env_mapping_forwarded(self):
        env = {"PATH": os.environ.get("PATH", ""), "SECSub_TEST_TOKEN": "tok123"}
        proc = SecureSubprocess.run(
            [sys.executable, "-c", "import os; print(os.environ['SECSub_TEST_TOKEN'])"],
            allowed_basenames=frozenset({os.path.basename(sys.executable)}),
            env=env,
        )
        assert "tok123" in proc.stdout

    def test_undecodable_bytes_replaced_not_crash(self):
        proc = SecureSubprocess.run(
            [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'a\\xffb')"],
            allowed_basenames=frozenset({os.path.basename(sys.executable)}),
            errors="replace",
        )
        assert proc.returncode == 0


class TestRunGit:
    def test_non_git_binary_rejected(self):
        with pytest.raises(ValueError, match="git executable required"):
            SecureSubprocess.run_git(["python", "--version"])

    def test_empty_argv_rejected(self):
        with pytest.raises(ValueError, match="git executable required"):
            SecureSubprocess.run_git([])

    def test_real_git_version(self):
        proc = SecureSubprocess.run_git(["git", "--version"])
        assert proc.returncode == 0
        assert "git version" in (proc.stdout or "").lower()


class TestRepoPythonScript:
    def test_missing_script_rejected(self):
        with pytest.raises(ValueError, match="existing .py"):
            SecureSubprocess.run_repo_python_script("does_not_exist_at_all.py", [])

    def test_non_py_file_rejected(self):
        rel = os.path.relpath(ROOT / "README.md", ROOT).replace(os.sep, "/")
        with pytest.raises(ValueError, match="existing .py"):
            SecureSubprocess.run_repo_python_script(rel, [])

    def test_traversal_outside_repo_rejected(self):
        # A real file that exists one level ABOVE the repo root (same drive)
        parent = ROOT.parent
        outside = parent / "_secsub_escape_probe.py"
        outside.write_text("print('hi')", encoding="utf-8")
        rel = os.path.relpath(outside, ROOT)
        try:
            with pytest.raises(ValueError, match="escapes repo root"):
                SecureSubprocess.run_repo_python_script(rel.replace(os.sep, "/"), [])
        finally:
            outside.unlink(missing_ok=True)

    def test_runs_existing_repo_script(self):
        temp_dir = ROOT / "tests" / ".pytest-temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        script = temp_dir / "probe_secsub.py"
        script.write_text("print('repo-script-ok')", encoding="utf-8")
        rel = os.path.relpath(script, ROOT).replace(os.sep, "/")
        proc = SecureSubprocess.run_repo_python_script(rel, ["arg1"])
        assert proc.returncode == 0
        assert "repo-script-ok" in proc.stdout


class TestRunPythonModule:
    def test_invalid_module_names_rejected(self):
        for bad in ("", "has space", "../evil", "dollar$", None):
            with pytest.raises(ValueError, match="invalid module"):
                SecureSubprocess.run_python_module(bad, [])

    def test_dotted_module_allowed(self):
        proc = SecureSubprocess.run_python_module("timeit", ["-h"])
        assert proc.returncode == 0

    def test_module_execution_output(self):
        proc = SecureSubprocess.run_python_module("zipapp", ["--help"])
        assert proc.returncode == 0
