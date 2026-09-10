"""Coverage tests for routes/ai_routes/specialized.py gaps.

Each test drives the route via the test client and targets one exact
listed production line:

- line 94: /ai/ask-genius with no JSON body -> 400
- line 123: /ai/quick-calc with no JSON body -> 400
- line 154: /ai/transformers-understand with no JSON body -> 400
"""

from unittest.mock import patch


class TestSpecializedCovAskGenius:
    def test_ask_genius_no_json_body_400_line94(self, ai_client):
        with patch(
            "routes.ai_routes.AIService.ask_genius",
            side_effect=AssertionError("must not be called"),
        ):
            resp = ai_client.post(
                "/ai/ask-genius",
                data=b"x",
                content_type="application/json",
            )
        assert resp.status_code == 400


class TestSpecializedCovQuickCalc:
    def test_quick_calc_no_json_body_400_line123(self, ai_client):
        with patch(
            "routes.ai_routes.AIService.quick_calculate",
            side_effect=AssertionError("must not be called"),
        ):
            resp = ai_client.post(
                "/ai/quick-calc",
                data=b"x",
                content_type="application/json",
            )
        assert resp.status_code == 400


class TestSpecializedCovTransformers:
    def test_transformers_no_json_body_400_line154(self, ai_client):
        with patch(
            "routes.ai_routes.AIService.understand_with_transformers",
            side_effect=AssertionError("must not be called"),
        ):
            resp = ai_client.post(
                "/ai/transformers-understand",
                data=b"x",
                content_type="application/json",
            )
        assert resp.status_code == 400
