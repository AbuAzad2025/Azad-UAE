"""Tests for neural_engine and vision_processor."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import pytest

from ai_knowledge.neural.neural_engine import AzadNeuralEngine, get_neural_engine
from ai_knowledge.neural.vision_processor import VisionProcessor, get_vision_processor


@pytest.fixture
def engine(tmp_path):
    with patch("ai_knowledge.get_knowledge_path", return_value=str(tmp_path)):
        return AzadNeuralEngine()


class TestAzadNeuralEngine:
    def test_ensure_models_dir(self, engine, tmp_path):
        assert os.path.isdir(engine.models_dir)

    def test_validate_accounting_balanced(self, engine):
        with patch.object(engine, "_load_model", return_value=False):
            result = engine.validate_accounting_entry(100, 100, 2, "Sale")
            assert result["is_correct"] is True

    def test_validate_accounting_unbalanced(self, engine):
        with patch.object(engine, "_load_model", return_value=False):
            result = engine.validate_accounting_entry(100, 50, 2, "Sale")
            assert result["is_correct"] is False

    def test_predict_optimal_price_regular(self, engine):
        with patch.object(engine, "_load_model", return_value=False):
            result = engine.predict_optimal_price(100, 1, "regular")
            assert result["predicted_price"] == 130.0

    def test_predict_optimal_price_partner(self, engine):
        with patch.object(engine, "_load_model", return_value=False):
            result = engine.predict_optimal_price(100, 1, "partner")
            assert result["predicted_price"] == pytest.approx(115.0)

    def test_detect_fraud_fallback(self, engine):
        with patch.object(engine, "_load_model", return_value=False):
            result = engine.detect_fraud({"amount_aed": 200000, "discount_amount": 120000, "subtotal": 200000})
            assert result["is_fraud"] is True

    def test_detect_fraud_normal(self, engine):
        with patch.object(engine, "_load_model", return_value=False):
            result = engine.detect_fraud({"amount_aed": 500, "discount_amount": 0, "subtotal": 500})
            assert result["is_fraud"] is False

    def test_understand_intent_sales(self, engine):
        result = engine.understand_intent("حلل المبيعات")
        assert result["intent"] == "sales_analysis"

    def test_get_status(self, engine):
        status = engine.get_status()
        assert "models" in status

    def test_singleton(self, tmp_path):
        with patch("ai_knowledge.get_knowledge_path", return_value=str(tmp_path)):
            import ai_knowledge.neural.neural_engine as mod

            mod._neural_engine_instance = None
            e1 = get_neural_engine()
            e2 = get_neural_engine()
            assert e1 is e2


class TestVisionProcessor:
    @pytest.fixture
    def processor(self):
        return VisionProcessor()

    def test_ocr_unavailable(self):
        with patch.object(VisionProcessor, "_check_ocr_availability", return_value=False):
            vp = VisionProcessor()
            result = vp.read_invoice_image("fake.png")
            assert result.get("confidence") == 0

    def test_read_invoice_missing_file(self, processor):
        result = processor.read_invoice_image("/nonexistent/invoice.png")
        assert result.get("confidence") == 0

    def test_read_invoice_valid_image(self, processor):
        from PIL import Image

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            Image.new("RGB", (10, 10), color="white").save(f.name)
            path = f.name
        try:
            result = processor.read_invoice_image(path)
            assert result.get("confidence", 0) > 0
        finally:
            os.unlink(path)

    def test_analyze_part_missing(self, processor):
        result = processor.analyze_part_image("/nonexistent/part.png")
        assert result.get("error") == "Image file not found"

    def test_extract_text(self, processor):
        assert isinstance(processor.extract_text_from_image("any.png"), str)

    def test_singleton(self):
        import ai_knowledge.neural.vision_processor as mod

        mod._vision_processor_instance = None
        v1 = get_vision_processor()
        v2 = get_vision_processor()
        assert v1 is v2
