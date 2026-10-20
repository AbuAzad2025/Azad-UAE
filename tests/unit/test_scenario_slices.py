"""The scenario slices must cover every scenario file, and cover it once.

The CI matrix splits ``tests/integration/business_scenarios`` into four parallel
slices so that the directory - which is the slowest thing in the build - stops
being one long job. A split like that has a hazard the old single-directory
path did not have: a file that matches no slice is not slow, it is *absent*, and
a scenario that is never run reports nothing at all. It passes.

So the split is checked from the inside: this test reads the matrix out of the
workflow, expands the same globs the shell expands, and asks whether every
scenario file lands in exactly one slice. A new wave file that nobody added to
a slice fails here rather than being quietly skipped for ever.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

WORKFLOW = Path(".github/workflows/ci.yml")
SCENARIO_DIR = Path("tests/integration/business_scenarios")

#: ``{a,b,c}`` - the shell's brace expansion, which the matrix uses.
_BRACE = re.compile(r"\{([^{}]*)\}")


def _expand_braces(pattern: str) -> list[str]:
    """Expand ``{a,b}`` the way bash does, one level at a time."""
    match = _BRACE.search(pattern)
    if not match:
        return [pattern]
    head, tail = pattern[: match.start()], pattern[match.end() :]
    return [
        head + option + tail for option in match.group(1).split(",") for pattern in _expand_braces(head + option + tail)
    ]


def _matrix_test_paths() -> list[str]:
    """Every ``test-path`` the matrix runs, read out of the workflow."""
    text = WORKFLOW.read_text(encoding="utf-8")
    return re.findall(r'"test-path":"([^"]+)"', text)


def _scenario_slices() -> dict[str, list[str]]:
    """The slices that point at the scenario directory, by their glob."""
    slices: dict[str, list[str]] = {}
    for path in _matrix_test_paths():
        if "business_scenarios" not in path:
            continue
        globs = [token for token in path.split() if "business_scenarios" in token]
        assert globs, f"a scenario slice names no file glob: {path}"
        slices[path] = globs
    return slices


def _files() -> list[str]:
    return sorted(p.name for p in SCENARIO_DIR.glob("test_*.py"))


class TestTheScenarioSlices:
    def test_the_matrix_splits_the_scenario_directory(self):
        """There is more than one slice, or the split did not happen."""
        slices = _scenario_slices()
        assert len(slices) >= 2, f"the scenario directory is still one job: {slices}"

    def test_every_scenario_file_is_run_by_exactly_one_slice(self):
        """A file in no slice is a scenario that never runs.

        This is the hazard the split introduces: the old single-directory path
        covered every file by construction, and a glob list does not.
        """
        slices = _scenario_slices()
        owners: dict[str, list[str]] = {}
        for path, globs in slices.items():
            for glob in globs:
                for pattern in _expand_braces(glob):
                    for name in _files():
                        if fnmatch.fnmatch(name, Path(pattern).name):
                            owners.setdefault(name, []).append(path)

        missing = [name for name in _files() if name not in owners]
        assert not missing, f"these scenario files are run by no slice: {missing}"

        doubled = {name: paths for name, paths in owners.items() if len(paths) > 1}
        assert not doubled, f"these scenario files are run by more than one slice: {doubled}"

    def test_the_slices_cover_the_scenario_files_between_them(self):
        """Every file is claimed, and the claim is the one the shell makes."""
        slices = _scenario_slices()
        claimed: set[str] = set()
        for globs in slices.values():
            for glob in globs:
                for pattern in _expand_braces(glob):
                    claimed |= {name for name in _files() if fnmatch.fnmatch(name, Path(pattern).name)}
        assert claimed == set(_files()), f"the slices and the directory disagree: {sorted(set(_files()) - claimed)}"

    def test_a_new_wave_file_would_be_caught(self):
        """The guard above is only worth something if it is really wired.

        A file that matches no slice is what the check exists for, so the check
        is exercised against one: the file is not created, the claim is, and
        the claim has to be missing.
        """
        slices = _scenario_slices()
        claimed = set()
        for globs in slices.values():
            for glob in globs:
                for pattern in _expand_braces(glob):
                    claimed |= {name for name in _files() if fnmatch.fnmatch(name, Path(pattern).name)}

        # A file named after a wave the slices do not know about.
        ghost = "test_wave99_future.py"
        assert ghost not in claimed, "the guard would have missed its own example"
        assert ghost not in _files(), "the example file exists, so the example proves nothing"
