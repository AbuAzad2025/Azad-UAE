"""Backup exec — allowlisted subprocess pipeline and validation guards."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


class TestValidatePgExecutable:
    """validate_pg_executable — allowlist enforcement."""

    @pytest.mark.parametrize("exe", ["pg_dump", "pg_dump.exe", "psql", "pg_restore.exe"])
    def test_allowlisted_tools_pass(self, exe):
        from services.backup_exec import validate_pg_executable

        assert validate_pg_executable(exe) == exe
        assert validate_pg_executable(f"/usr/bin/{exe}") == f"/usr/bin/{exe}"

    def test_rejects_empty_path(self):
        from services.backup_exec import validate_pg_executable

        with pytest.raises(ValueError, match="empty"):
            validate_pg_executable("")

    def test_rejects_non_allowlisted_binary(self):
        from services.backup_exec import validate_pg_executable

        with pytest.raises(ValueError, match="not allowlisted"):
            validate_pg_executable("rm")


class TestRunPgTool:
    """run_pg_tool — compression pipeline success and permission failures."""

    def test_successful_pg_dump_invocation(self, mocker):
        completed = subprocess.CompletedProcess(["pg_dump"], 0, stdout="ok", stderr="")
        mock_run = mocker.patch("utils.secure_subprocess.subprocess.run", return_value=completed)

        from services.backup_exec import run_pg_tool

        result = run_pg_tool(["pg_dump", "-Fc", "mydb"], env={"PGPASSWORD": "x"}, timeout=60)
        assert result.returncode == 0
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["shell"] is False

    def test_permission_denied_propagates(self, mocker):
        mocker.patch(
            "utils.secure_subprocess.subprocess.run",
            side_effect=PermissionError("filesystem write denied"),
        )

        from services.backup_exec import run_pg_tool

        with pytest.raises(PermissionError, match="write denied"):
            run_pg_tool(["pg_dump", "db"])

    def test_empty_argv_rejected(self):
        from services.backup_exec import run_pg_tool

        with pytest.raises(ValueError, match="argv required"):
            run_pg_tool([])


class TestRunGit:
    """run_git — repo metadata subprocess."""

    def test_git_success(self, mocker):
        completed = subprocess.CompletedProcess(["git"], 0, stdout="abc123", stderr="")
        mocker.patch("utils.secure_subprocess.subprocess.run", return_value=completed)

        from services.backup_exec import run_git

        result = run_git(["git", "rev-parse", "HEAD"], cwd="/repo")
        assert result.stdout == "abc123"

    def test_invalid_git_executable(self):
        from services.backup_exec import run_git

        with pytest.raises(ValueError, match="git executable"):
            run_git(["bash", "-c", "evil"])


class TestRunRepoPythonScript:
    """run_repo_python_script — path escape guard."""

    def test_runs_existing_script_under_repo(self, mocker, tmp_path):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        script_rel = "scripts/verify_backup.py"
        script_abs = os.path.join(root, script_rel.replace("/", os.sep))
        if not os.path.isfile(script_abs):
            pytest.skip("verify_backup.py not in repo")

        completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        mocker.patch("utils.secure_subprocess.subprocess.run", return_value=completed)

        from services.backup_exec import run_repo_python_script

        result = run_repo_python_script(script_rel, ["--help"])
        assert result.returncode == 0

    def test_rejects_path_outside_repo(self, mocker):
        mocker.patch("utils.secure_subprocess.os.path.isfile", return_value=True)

        from services.backup_exec import run_repo_python_script

        with pytest.raises(ValueError, match="escapes repo"):
            run_repo_python_script("../outside_assurance.py", [])

    def test_rejects_missing_script(self):
        from services.backup_exec import run_repo_python_script

        with pytest.raises(ValueError, match="existing .py"):
            run_repo_python_script("nonexistent_script_xyz.py", [])


class TestRunPythonModule:
    """run_python_module — module runner pipeline."""

    def test_invalid_module_name_rejected(self):
        from services.backup_exec import run_python_module

        with pytest.raises(ValueError, match="invalid module"):
            run_python_module("os;rm", [])

    def test_module_invocation_success(self, mocker):
        completed = subprocess.CompletedProcess([], 0, stdout="done", stderr="")
        mock_run = mocker.patch("utils.secure_subprocess.subprocess.run", return_value=completed)

        from services.backup_exec import run_python_module

        run_python_module("pytest", ["--version"])
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == sys.executable
        assert cmd[1] == "-m"
        assert cmd[2] == "pytest"

    def test_repo_script_passes_env_and_cwd(self, mocker, tmp_path):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        script_rel = "scripts/verify_backup.py"
        script_abs = os.path.join(root, script_rel.replace("/", os.sep))
        if not os.path.isfile(script_abs):
            script_abs = os.path.join(root, "tests", ".pytest-temp", "tmp_script.py")
            os.makedirs(os.path.dirname(script_abs), exist_ok=True)
            with open(script_abs, "w", encoding="utf-8") as fh:
                fh.write('print("ok")\n')
            script_rel = os.path.relpath(script_abs, root).replace("\\", "/")
        completed = subprocess.CompletedProcess([], 0, stdout="ok", stderr="")
        mock_run = mocker.patch("utils.secure_subprocess.subprocess.run", return_value=completed)
        from services.backup_exec import run_repo_python_script

        result = run_repo_python_script(script_rel, ["--dry-run"], env={"FOO": "bar"}, cwd=str(tmp_path))
        assert result.returncode == 0
        assert mock_run.call_args.kwargs["env"] == {"FOO": "bar"}
        assert mock_run.call_args.kwargs["cwd"] == str(tmp_path)
