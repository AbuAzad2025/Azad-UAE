"""Unit tests for ai_knowledge/analytics/market_insights.py — content integrity."""

from __future__ import annotations

from ai_knowledge.analytics.market_insights import MARKET_INSIGHTS, get_market_insights


class TestMarketInsightsStructure:
    def test_top_level_sections(self):
        assert set(MARKET_INSIGHTS) == {
            "uae_market",
            "pricing_strategy",
            "competitors",
            "trends",
        }

    def test_uae_market_content(self):
        uae = MARKET_INSIGHTS["uae_market"]
        assert set(uae) == {"construction_sector", "automotive_sector", "peak_seasons"}
        assert uae["construction_sector"]
        assert uae["automotive_sector"]
        assert len(uae["peak_seasons"]) == 4
        assert all(isinstance(s, str) and s for s in uae["peak_seasons"])

    def test_pricing_strategy_tiers(self):
        pricing = MARKET_INSIGHTS["pricing_strategy"]
        assert set(pricing) == {"individuals", "merchants", "partners", "vip"}
        for tier, text in pricing.items():
            assert isinstance(text, str) and text, tier
            assert "%" in text, tier

    def test_competitors_content(self):
        competitors = MARKET_INSIGHTS["competitors"]
        assert set(competitors) == {"strengths", "weaknesses"}
        assert competitors["strengths"]
        assert competitors["weaknesses"]

    def test_trends_content(self):
        trends = MARKET_INSIGHTS["trends"]
        assert len(trends) == 5
        assert all(isinstance(t, str) and t for t in trends)


class TestGetMarketInsights:
    def test_returns_formatted_arabic_string(self):
        text = get_market_insights()
        assert isinstance(text, str)
        assert "فهم السوق" in text
        assert "استراتيجية التسعير" in text

    def test_includes_every_pricing_tier(self):
        text = get_market_insights()
        for tier, value in MARKET_INSIGHTS["pricing_strategy"].items():
            assert f"• {tier}: {value}" in text

    def test_mentions_core_sectors(self):
        text = get_market_insights()
        assert "الإنشاءات" in text
        assert "السيارات" in text
