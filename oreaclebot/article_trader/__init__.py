"""
Article Trader - News-driven prediction market trading system.

This module connects enriched articles from Snowflake to Manifold Markets,
using LLM analysis to find trading opportunities.
"""

from .snowflake_source import SnowflakeArticleSource, Article
from .market_matcher import MarketMatcher, MarketMatch
from .analyzer import ArticleMarketAnalyzer, TradingSignal
from .trader import ArticleTrader, TradingSession
from .cli import main

__all__ = [
    "SnowflakeArticleSource",
    "Article",
    "MarketMatcher",
    "MarketMatch",
    "ArticleMarketAnalyzer",
    "TradingSignal",
    "ArticleTrader",
    "TradingSession",
    "main",
]
