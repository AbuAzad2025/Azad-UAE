"""Tests for ai_knowledge path helpers."""
from __future__ import annotations

import os

from ai_knowledge import (
    AI_KNOWLEDGE_DIR,
    get_expanded_path,
    get_knowledge_path,
    get_model_path,
    get_training_path,
)


class TestKnowledgePaths:
    def test_knowledge_dir_exists(self):
        assert os.path.isdir(AI_KNOWLEDGE_DIR)

    def test_get_training_path(self):
        path = get_training_path('sample.json')
        assert path.endswith(os.path.join('data', 'training', 'sample.json'))

    def test_get_model_path(self):
        path = get_model_path('model.bin')
        assert 'data' in path and 'models' in path

    def test_get_expanded_path(self):
        path = get_expanded_path('expanded.json')
        assert 'expanded' in path

    def test_get_knowledge_path_fallback(self):
        path = get_knowledge_path('nonexistent-file-xyz.json')
        assert path.startswith(AI_KNOWLEDGE_DIR)
