"""
Consolidated module: analytics_engine.py
Re-exports from ai_knowledge.analytics sub-package (single source of truth).
"""

from ai_knowledge.analytics.data_analyzer import DataAnalyzer, data_analyzer
from ai_knowledge.analytics.analytics_predictions import (
    SalesAnalytics,
    InventoryAnalytics,
    ProfitAnalytics,
    CashFlowAnalytics,
    get_analytics,
)
from ai_knowledge.analytics.market_insights import get_market_insights

__all__ = [
    'DataAnalyzer', 'data_analyzer',
    'SalesAnalytics', 'InventoryAnalytics', 'ProfitAnalytics', 'CashFlowAnalytics',
    'get_analytics', 'get_market_insights',
]
