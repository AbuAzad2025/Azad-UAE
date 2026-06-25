"""Tests for semantic_matcher and transformers_brain."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from ai_knowledge.neural.semantic_matcher import (
    SemanticMatcher,
    get_confidence,
    get_intent,
    semantic_matcher,
    understand_message,
)
from ai_knowledge.neural.transformers_brain import TransformersBrain, get_transformers_brain


class TestSemanticMatcher:
    @pytest.fixture
    def matcher(self):
        return SemanticMatcher()

    def test_exact_invoice_intent(self, matcher):
        result = matcher.smart_match('فاتورة جديدة')
        assert result['intent'] == 'create_invoice'

    def test_fuzzy_match_identical(self, matcher):
        assert matcher.fuzzy_match('cat', 'cat') == 1.0

    def test_module_helpers(self):
        assert 'intent' in understand_message('فاتورة جديدة')
        assert get_intent('فاتورة جديدة') is not None
        assert get_confidence('فاتورة جديدة') >= 0.0

    def test_singleton(self):
        assert semantic_matcher is not None


class TestTransformersBrain:
    @pytest.fixture
    def brain(self):
        return TransformersBrain(vocab_size=100, d_model=64, n_heads=4)

    def test_self_attention_length(self, brain):
        q = [1.0, 0.5, 0.2, 0.1]
        assert len(brain.self_attention(q, q, q)) == len(q)

    def test_positional_encoding(self, brain):
        assert len(brain.positional_encoding(0, brain.d_model)) == brain.d_model

    def test_understand_tax_question(self, brain):
        result = brain.understand('كم الضريبة؟')
        assert result['intent'] == 'question'

    def test_generate_response_tax(self, brain):
        response = brain.generate_response('كم الضريبة؟')
        assert isinstance(response, str) and len(response) > 0

    def test_context_trim(self, brain):
        for i in range(25):
            brain.add_to_context(f'msg {i}')
        assert len(brain.context_memory) <= 20

    def test_context_summary(self, brain):
        assert isinstance(brain.get_context_summary(), str)

    def test_transformer_block(self, brain):
        inp = [0.1] * brain.d_model
        out = brain.transformer_block(inp, 0)
        assert len(out) == brain.d_model

    def test_singleton(self):
        import ai_knowledge.neural.transformers_brain as mod
        mod._transformers_brain_instance = None
        b1 = get_transformers_brain()
        b2 = get_transformers_brain()
        assert b1 is b2
