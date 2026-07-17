"""Analytics & predictions."""

from ai_knowledge.analytics.data_analyzer import data_analyzer
from ai_knowledge.analytics.analytics_predictions import (
    SalesAnalytics,
    InventoryAnalytics,
    ProfitAnalytics,
    CashFlowAnalytics,
    get_analytics,
)
from ai_knowledge.analytics.market_insights import get_market_insights

__all__ = [
    "data_analyzer",
    "SalesAnalytics",
    "InventoryAnalytics",
    "ProfitAnalytics",
    "CashFlowAnalytics",
    "get_analytics",
    "get_market_insights",
]
