"""Coverage tests for vision_processor analyze_part_image error path 149-151."""

from __future__ import annotations

from unittest.mock import patch

from ai_knowledge.neural.vision_processor import VisionProcessor


class TestCovVisionProcessorError:
    def test_analyze_part_image_exception_returns_error_149_151(self):
        with patch("os.path.isabs", side_effect=RuntimeError("fs boom")):
            result = VisionProcessor.analyze_part_image("any.png")
        assert result["error"] == "fs boom"

    def test_analyze_part_image_abspath_exception_returns_error(self):
        with patch("os.path.abspath", side_effect=OSError("path boom")):
            result = VisionProcessor.analyze_part_image("relative/part.png")
        assert result["error"] == "path boom"
