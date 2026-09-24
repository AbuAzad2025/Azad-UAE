"""Gap100 for routes/ai_routes/knowledge.py — empty-body 400 arcs (100, 189, 208)."""

from __future__ import annotations

from unittest.mock import patch


class TestKnowledgeEmptyBody:
    def test_set_goal_empty_body_400(self, ai_client):
        with patch("routes.ai_routes.knowledge.knowledge_expander"):
            resp = ai_client.post(
                "/ai/improvement/set-goal",
                data="",
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_add_website_empty_body_400(self, ai_client):
        with (
            patch("routes.ai_routes.knowledge.knowledge_expander"),
            patch("utils.decorators.is_global_owner_user", return_value=True),
        ):
            resp = ai_client.post(
                "/ai/knowledge/add-website",
                data="",
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_add_website_missing_url_400(self, ai_client):
        with (
            patch("routes.ai_routes.knowledge.knowledge_expander"),
            patch("utils.decorators.is_global_owner_user", return_value=True),
        ):
            resp = ai_client.post(
                "/ai/knowledge/add-website",
                json={"category": "general", "description": "docs"},
            )
        assert resp.status_code == 400
        assert "الرابط" in resp.get_json()["message"]

    def test_add_document_empty_body_400(self, ai_client):
        with (
            patch("routes.ai_routes.knowledge.knowledge_expander"),
            patch("utils.decorators.is_global_owner_user", return_value=True),
        ):
            resp = ai_client.post(
                "/ai/knowledge/add-document",
                data="",
                content_type="application/json",
            )
        assert resp.status_code == 400
