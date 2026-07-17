"""Import smoke tests for every ai_knowledge Python module."""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import ai_knowledge

_SKIP = {
    "ai_knowledge.trainer",  # heavy side effects on import in some envs
}

_MODULES = sorted(
    name
    for _finder, name, _ispkg in pkgutil.walk_packages(
        ai_knowledge.__path__, ai_knowledge.__name__ + "."
    )
    if name not in _SKIP and not name.endswith(".tests")
)


@pytest.mark.parametrize("module_name", _MODULES)
def test_ai_knowledge_module_imports(module_name):
    importlib.import_module(module_name)
