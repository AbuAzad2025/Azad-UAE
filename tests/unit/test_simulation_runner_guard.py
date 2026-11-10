"""The unfinished simulation must not write to a configured database."""

import subprocess
import sys
from pathlib import Path


def test_unfinished_simulation_refuses_direct_execution():
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_5k_real_world_simulation.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, check=False, timeout=10)

    assert result.returncode != 0
    assert "simulation disabled" in result.stderr.lower()
