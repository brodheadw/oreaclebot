"""
Snowflake Article Source - Fetches enriched articles from MIKHAIL.PUBLIC.ARTICLE.

This module provides access to news articles that have been enriched with:
- Metal/commodity relevance
- Market impact assessment
- Entity extraction
- Confidence scores
"""

import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Generator, List, Optional, Dict, Any

import snowflake.connector
from snowflake.connector import SnowflakeConnection


@dataclass
class Article:
    """Represents an enriched article from Snowflake."""
    id: int
    title: str
    url: str
    body: str
    article_date: Optional[datetime]
    source: Optional[str]

    # Enrichment fields
    metal: Optional[str] = None
    impact_mechanism: Optional[str] = None
    detailed_analysis: Optional[str] = None
    confidence: Optional[float] = None
    market_impact: Optional[str] = None  # 'high', 'medium', 'low', 'none'
    supply_impact: Optional[float] = None
    demand_impact: Optional[float] = None
    impact_probability: Optional[float] = None
    timeframe_months: Optional[int] = None
    enriched_at: Optional[datetime] = None

    def has_trading_signal(self) -> bool:
        """Check if article has meaningful trading signal."""
        if not self.confidence or self.confidence < 0.5:
            return False
        if not self.market_impact or self.market_impact == 'none':
            return False
        return True

    def get_search_terms(self) -> List[str]:
        """Extract search terms for finding related markets."""
        terms = []

        if self.metal:
            terms.append(self.metal.lower())

        # Extract key terms from title
        title_words = self.title.lower().split()
        commodity_keywords = [
            'gold', 'silver', 'copper', 'lithium', 'nickel', 'zinc', 'aluminum',
            'platinum', 'palladium', 'rhodium', 'iron', 'steel', 'cobalt',
            'uranium', 'oil', 'gas', 'coal', 'wheat', 'corn', 'soybean'
        ]
        for word in title_words:
            if word in commodity_keywords and word not in terms:
                terms.append(word)

        return terms

    def __str__(self) -> str:
        return f"Article({self.id}): {self.title[:60]}..."


def get_snowflake_credentials() -> dict:
    """
    Get Snowflake credentials from environment variables.

    Required:
        SNOWFLAKE_USER
        SNOWFLAKE_PASSWORD
        SNOWFLAKE_ACCOUNT

    Optional:
        SNOWFLAKE_WAREHOUSE (default: COMPUTE_WH)
        SNOWFLAKE_DATABASE (default: MIKHAIL)
        SNOWFLAKE_SCHEMA (default: PUBLIC)
        SNOWFLAKE_ROLE (default: ACCOUNTADMIN)
    """
    required_vars = ['SNOWFLAKE_USER', 'SNOWFLAKE_PASSWORD', 'SNOWFLAKE_ACCOUNT']
    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return {
        'user': os.getenv('SNOWFLAKE_USER'),
        'password': os.getenv('SNOWFLAKE_PASSWORD'),
        'account': os.getenv('SNOWFLAKE_ACCOUNT'),
        'warehouse': os.getenv('SNOWFLAKE_WAREHOUSE', 'COMPUTE_WH'),
        'database': os.getenv('SNOWFLAKE_DATABASE', 'MIKHAIL'),
        'schema': os.getenv('SNOWFLAKE_SCHEMA', 'PUBLIC'),
        'role': os.getenv('SNOWFLAKE_ROLE', 'ACCOUNTADMIN')
    }


@contextmanager
def get_snowflake_connection() -> Generator[SnowflakeConnection, None, None]:
    """Context manager for Snowflake connections."""
    credentials = get_snowflake_credentials()
    conn = snowflake.connector.connect(**credentials)

    try:
        yield conn
    finally:
        conn.close()


class SnowflakeArticleSource:
    """
    Fetches enriched articles from Snowflake for trading analysis.
    """

    def __init__(self):
        """Initialize the article source."""
        self.credentials = get_snowflake_credentials()

    def fetch_recent_articles(
        self,
        days: int = 7,
        limit: int = 100,
        min_confidence: float = 0.5,
        market_impact: Optional[List[str]] = None
    ) -> List[Article]:
        """
        Fetch recent enriched articles.

        Args:
            days: Number of days back to fetch
            limit: Maximum number of articles
            min_confidence: Minimum confidence score
            market_impact: Filter by market impact level (e.g., ['high', 'medium'])

        Returns:
            List of Article objects
        """
        market_impact = market_impact or ['high', 'medium']

        with get_snowflake_connection() as conn:
            cursor = conn.cursor()

            # Build query with filters
            impact_filter = "', '".join(market_impact)
            query = f"""
                SELECT
                    ID,
                    TITLE,
                    URL,
                    BODY,
                    ARTICLE_DATE,
                    SOURCE,
                    METAL,
                    IMPACT_MECHANISM,
                    DETAILED_ANALYSIS,
                    CONFIDENCE,
                    MARKET_IMPACT,
                    SUPPLY_IMPACT,
                    DEMAND_IMPACT,
                    IMPACT_PROBABILITY,
                    TIMEFRAME_MONTHS,
                    ENRICHED_AT
                FROM MIKHAIL.PUBLIC.ARTICLE
                WHERE ENRICHED_AT IS NOT NULL
                AND ARTICLE_DATE >= DATEADD(day, -{days}, CURRENT_DATE())
                AND CONFIDENCE >= {min_confidence}
                AND MARKET_IMPACT IN ('{impact_filter}')
                ORDER BY ARTICLE_DATE DESC
                LIMIT {limit}
            """

            cursor.execute(query)

            articles = []
            for row in cursor.fetchall():
                article = Article(
                    id=row[0],
                    title=row[1] or "",
                    url=row[2] or "",
                    body=row[3] or "",
                    article_date=row[4],
                    source=row[5],
                    metal=row[6],
                    impact_mechanism=row[7],
                    detailed_analysis=row[8],
                    confidence=row[9],
                    market_impact=row[10],
                    supply_impact=row[11],
                    demand_impact=row[12],
                    impact_probability=row[13],
                    timeframe_months=row[14],
                    enriched_at=row[15]
                )
                articles.append(article)

            return articles

    def fetch_article_by_id(self, article_id: int) -> Optional[Article]:
        """Fetch a specific article by ID."""
        with get_snowflake_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT
                    ID, TITLE, URL, BODY, ARTICLE_DATE, SOURCE,
                    METAL, IMPACT_MECHANISM, DETAILED_ANALYSIS,
                    CONFIDENCE, MARKET_IMPACT, SUPPLY_IMPACT,
                    DEMAND_IMPACT, IMPACT_PROBABILITY, TIMEFRAME_MONTHS, ENRICHED_AT
                FROM MIKHAIL.PUBLIC.ARTICLE
                WHERE ID = %s
            """

            cursor.execute(query, (article_id,))
            row = cursor.fetchone()

            if not row:
                return None

            return Article(
                id=row[0],
                title=row[1] or "",
                url=row[2] or "",
                body=row[3] or "",
                article_date=row[4],
                source=row[5],
                metal=row[6],
                impact_mechanism=row[7],
                detailed_analysis=row[8],
                confidence=row[9],
                market_impact=row[10],
                supply_impact=row[11],
                demand_impact=row[12],
                impact_probability=row[13],
                timeframe_months=row[14],
                enriched_at=row[15]
            )

    def fetch_unprocessed_articles(
        self,
        processed_ids: set,
        days: int = 3,
        limit: int = 50
    ) -> List[Article]:
        """
        Fetch articles that haven't been processed for trading yet.

        Args:
            processed_ids: Set of article IDs already processed
            days: Days back to look
            limit: Max articles to return

        Returns:
            List of unprocessed articles
        """
        articles = self.fetch_recent_articles(days=days, limit=limit * 2)

        # Filter out already processed
        unprocessed = [a for a in articles if a.id not in processed_ids]

        return unprocessed[:limit]

    def get_articles_by_metal(self, metal: str, days: int = 30, limit: int = 50) -> List[Article]:
        """Fetch articles for a specific metal/commodity."""
        with get_snowflake_connection() as conn:
            cursor = conn.cursor()

            query = f"""
                SELECT
                    ID, TITLE, URL, BODY, ARTICLE_DATE, SOURCE,
                    METAL, IMPACT_MECHANISM, DETAILED_ANALYSIS,
                    CONFIDENCE, MARKET_IMPACT, SUPPLY_IMPACT,
                    DEMAND_IMPACT, IMPACT_PROBABILITY, TIMEFRAME_MONTHS, ENRICHED_AT
                FROM MIKHAIL.PUBLIC.ARTICLE
                WHERE ENRICHED_AT IS NOT NULL
                AND LOWER(METAL) = LOWER(%s)
                AND ARTICLE_DATE >= DATEADD(day, -{days}, CURRENT_DATE())
                ORDER BY ARTICLE_DATE DESC
                LIMIT {limit}
            """

            cursor.execute(query, (metal,))

            articles = []
            for row in cursor.fetchall():
                articles.append(Article(
                    id=row[0],
                    title=row[1] or "",
                    url=row[2] or "",
                    body=row[3] or "",
                    article_date=row[4],
                    source=row[5],
                    metal=row[6],
                    impact_mechanism=row[7],
                    detailed_analysis=row[8],
                    confidence=row[9],
                    market_impact=row[10],
                    supply_impact=row[11],
                    demand_impact=row[12],
                    impact_probability=row[13],
                    timeframe_months=row[14],
                    enriched_at=row[15]
                ))

            return articles


def test_connection() -> bool:
    """Test Snowflake connection and article access."""
    try:
        with get_snowflake_connection() as conn:
            cursor = conn.cursor()

            # Test connection
            cursor.execute("SELECT CURRENT_VERSION()")
            version = cursor.fetchone()[0]
            print(f"Connected to Snowflake version {version}")

            # Test article table
            cursor.execute("""
                SELECT COUNT(*)
                FROM MIKHAIL.PUBLIC.ARTICLE
                WHERE ENRICHED_AT IS NOT NULL
            """)
            count = cursor.fetchone()[0]
            print(f"Found {count} enriched articles")

            return True

    except Exception as e:
        print(f"Connection failed: {e}")
        return False


if __name__ == '__main__':
    test_connection()
