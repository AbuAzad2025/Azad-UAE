"""Coverage tests for transformers_brain positional-encoding odd-dim arc 204->198."""

from __future__ import annotations

from ai_knowledge.neural.transformers_brain import TransformersBrain


class TestCovTransformersBrainOddDims:
    def test_positional_encoding_odd_d_model_204_198(self):
        # 204->198: with an odd d_model the final loop iteration has
        # i + 1 == d_model, so the cos branch is skipped and the loop
        # continues back to line 198.
        encoding = TransformersBrain.positional_encoding(3, 7)
        assert len(encoding) == 7

    def test_positional_encoding_single_dim_204_198(self):
        encoding = TransformersBrain.positional_encoding(0, 1)
        assert len(encoding) == 1
