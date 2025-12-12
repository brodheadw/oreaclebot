"""
Market Matcher - Finds relevant Manifold Markets for articles.

Uses both keyword search and LLM analysis to find prediction markets
that could be affected by news articles.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import requests

from .snowflake_source import Article

logger = logging.getLogger(__name__)


@dataclass
class MarketMatch:
    """A potential match between an article and a market."""
    market: Dict[str, Any]
    article: Article
    relevance_score: float  # 0-1 score of how relevant the match is
    match_reason: str
    search_term: str

    @property
    def market_id(self) -> str:
        return self.market.get('id', '')

    @property
    def question(self) -> str:
        return self.market.get('question', '')

    @property
    def probability(self) -> float:
        return self.market.get('probability', 0.5)

    @property
    def is_binary(self) -> bool:
        return self.market.get('outcomeType') == 'BINARY'

    @property
    def is_tradeable(self) -> bool:
        """Check if market is open for trading."""
        if self.market.get('isResolved', False):
            return False
        close_time = self.market.get('closeTime')
        if close_time and close_time < time.time() * 1000:
            return False
        return True


class ManifoldSearchClient:
    """Lightweight client for searching Manifold Markets."""

    BASE_URL = "https://api.manifold.markets/v0"

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "OreacleBot/2.0",
            "Accept": "application/json"
        })

    def search_markets(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search markets by query string."""
        try:
            response = self.session.get(
                f"{self.BASE_URL}/search-markets",
                params={"term": query, "limit": limit},
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.warning(f"Search failed for '{query}': {e}")
            return []

    def get_market(self, market_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific market by ID."""
        try:
            response = self.session.get(
                f"{self.BASE_URL}/market/{market_id}",
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.warning(f"Failed to get market {market_id}: {e}")
            return None

    def get_markets_by_user(self, username: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all markets by a specific user."""
        all_markets = []
        before_cursor = None

        while True:
            params = {"limit": min(limit, 1000)}
            if before_cursor:
                params["before"] = before_cursor

            try:
                response = self.session.get(
                    f"{self.BASE_URL}/markets",
                    params=params,
                    timeout=self.timeout
                )
                response.raise_for_status()
                markets = response.json()

                if not markets:
                    break

                # Filter by username
                user_markets = [m for m in markets if m.get('creatorUsername') == username]
                all_markets.extend(user_markets)

                if len(all_markets) >= limit or len(markets) < 1000:
                    break

                before_cursor = markets[-1]["id"]

            except requests.RequestException as e:
                logger.warning(f"Failed to get markets for {username}: {e}")
                break

        return all_markets[:limit]


class MarketMatcher:
    """
    Finds relevant prediction markets for news articles.

    Uses multiple strategies:
    1. Keyword search based on article metadata
    2. Entity-based search
    3. Pre-defined market watchlists
    """

    # Monitored market creators (their markets are always considered)
    MONITORED_USERS = [
        "MikhailTal",
        "BoltonBailey",
        "JoshDreckmeyr",
    ]

    # Keywords that indicate commodity/market relevance
    COMMODITY_KEYWORDS = {
        'gold': ['gold', 'gold price', 'gold mining', 'bullion'],
        'silver': ['silver', 'silver price', 'silver mining'],
        'copper': ['copper', 'copper price', 'copper mining', 'freeport'],
        'lithium': ['lithium', 'lithium price', 'lithium mining', 'catl', 'battery'],
        'nickel': ['nickel', 'nickel price', 'nickel mining', 'indonesia nickel'],
        'palladium': ['palladium', 'palladium price', 'pgm', 'norilsk'],
        'platinum': ['platinum', 'platinum price', 'pgm'],
        'oil': ['oil', 'crude oil', 'brent', 'wti', 'opec'],
        'uranium': ['uranium', 'nuclear', 'cameco', 'kazatomprom'],
    }

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the market matcher.

        Args:
            api_key: Optional Manifold API key (not required for searches)
        """
        self.client = ManifoldSearchClient()
        self.api_key = api_key
        self._market_cache: Dict[str, Dict[str, Any]] = {}
        self._user_markets_cache: Dict[str, List[Dict[str, Any]]] = {}

    def find_markets_for_article(
        self,
        article: Article,
        max_markets: int = 10,
        include_monitored_users: bool = True
    ) -> List[MarketMatch]:
        """
        Find relevant markets for an article.

        Args:
            article: The article to find markets for
            max_markets: Maximum number of markets to return
            include_monitored_users: Whether to include markets from monitored users

        Returns:
            List of MarketMatch objects sorted by relevance
        """
        matches: List[MarketMatch] = []
        seen_market_ids: set = set()

        # Strategy 1: Search by metal/commodity if present
        if article.metal:
            metal_lower = article.metal.lower()
            search_terms = self.COMMODITY_KEYWORDS.get(metal_lower, [metal_lower])

            for term in search_terms[:3]:  # Limit searches
                markets = self.client.search_markets(term, limit=20)
                for market in markets:
                    if market.get('id') not in seen_market_ids:
                        seen_market_ids.add(market.get('id'))
                        match = MarketMatch(
                            market=market,
                            article=article,
                            relevance_score=self._calculate_relevance(article, market, term),
                            match_reason=f"Metal keyword match: {term}",
                            search_term=term
                        )
                        if match.is_binary and match.is_tradeable:
                            matches.append(match)

        # Strategy 2: Search by extracted terms from title
        search_terms = article.get_search_terms()
        for term in search_terms[:2]:
            if term != article.metal:  # Avoid duplicate searches
                markets = self.client.search_markets(term, limit=10)
                for market in markets:
                    if market.get('id') not in seen_market_ids:
                        seen_market_ids.add(market.get('id'))
                        match = MarketMatch(
                            market=market,
                            article=article,
                            relevance_score=self._calculate_relevance(article, market, term),
                            match_reason=f"Title keyword match: {term}",
                            search_term=term
                        )
                        if match.is_binary and match.is_tradeable:
                            matches.append(match)

        # Strategy 3: Include markets from monitored users
        if include_monitored_users:
            for username in self.MONITORED_USERS:
                user_markets = self._get_user_markets_cached(username)
                for market in user_markets:
                    if market.get('id') not in seen_market_ids:
                        relevance = self._calculate_relevance(article, market, "monitored_user")
                        if relevance > 0.3:  # Only include if somewhat relevant
                            seen_market_ids.add(market.get('id'))
                            match = MarketMatch(
                                market=market,
                                article=article,
                                relevance_score=relevance,
                                match_reason=f"Monitored user: {username}",
                                search_term=username
                            )
                            if match.is_binary and match.is_tradeable:
                                matches.append(match)

        # Sort by relevance and return top matches
        matches.sort(key=lambda m: m.relevance_score, reverse=True)
        return matches[:max_markets]

    def _get_user_markets_cached(self, username: str) -> List[Dict[str, Any]]:
        """Get user markets with caching."""
        if username not in self._user_markets_cache:
            self._user_markets_cache[username] = self.client.get_markets_by_user(username, limit=50)
        return self._user_markets_cache[username]

    def _calculate_relevance(self, article: Article, market: Dict[str, Any], search_term: str) -> float:
        """
        Calculate relevance score between article and market.

        Returns:
            Float between 0 and 1
        """
        score = 0.0
        question = market.get('question', '').lower()
        description = market.get('description', '').lower()
        text = f"{question} {description}"

        # Metal/commodity match
        if article.metal:
            metal_lower = article.metal.lower()
            if metal_lower in text:
                score += 0.4
            # Check related terms
            related = self.COMMODITY_KEYWORDS.get(metal_lower, [])
            if any(term in text for term in related):
                score += 0.2

        # Title keyword overlap
        title_words = set(article.title.lower().split())
        question_words = set(question.split())
        overlap = len(title_words & question_words)
        if overlap > 2:
            score += min(0.3, overlap * 0.1)

        # Market impact alignment
        # If article says high impact and market is about prices, increase score
        if article.market_impact == 'high':
            price_keywords = ['price', 'cost', '$', 'increase', 'decrease', 'rise', 'fall']
            if any(kw in text for kw in price_keywords):
                score += 0.2

        # Timeframe alignment
        if article.timeframe_months:
            close_time = market.get('closeTime')
            if close_time:
                # Check if market closes within article's timeframe
                months_to_close = (close_time / 1000 - time.time()) / (30 * 24 * 3600)
                if 0 < months_to_close <= article.timeframe_months * 1.5:
                    score += 0.1

        return min(1.0, score)

    def get_market_details(self, market_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed market information."""
        if market_id in self._market_cache:
            return self._market_cache[market_id]

        market = self.client.get_market(market_id)
        if market:
            self._market_cache[market_id] = market
        return market

    def clear_cache(self):
        """Clear all caches."""
        self._market_cache.clear()
        self._user_markets_cache.clear()
