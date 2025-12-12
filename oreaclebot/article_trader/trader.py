"""
Article Trader - Executes trades based on article-derived signals.

This module ties together article fetching, market matching, analysis,
and trade execution into a complete trading pipeline.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
import json
import requests

from .snowflake_source import SnowflakeArticleSource, Article
from .market_matcher import MarketMatcher, MarketMatch
from .analyzer import ArticleMarketAnalyzer, TradingSignal, Direction

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Record of an executed trade."""
    signal: TradingSignal
    outcome: str  # "YES" or "NO"
    amount: float
    timestamp: datetime
    success: bool
    error: Optional[str] = None
    bet_response: Optional[Dict[str, Any]] = None


@dataclass
class TradingSession:
    """Results of a trading session."""
    start_time: datetime
    end_time: Optional[datetime] = None
    articles_processed: int = 0
    markets_matched: int = 0
    signals_generated: int = 0
    trades_executed: int = 0
    trades_failed: int = 0
    initial_balance: float = 0.0
    final_balance: float = 0.0
    trades: List[Trade] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """Generate session summary."""
        duration = (self.end_time - self.start_time).total_seconds() if self.end_time else 0
        return f"""
Trading Session Summary
=======================
Duration: {duration:.1f}s
Articles processed: {self.articles_processed}
Markets matched: {self.markets_matched}
Signals generated: {self.signals_generated}
Trades executed: {self.trades_executed}
Trades failed: {self.trades_failed}
Balance: {self.initial_balance:.2f} -> {self.final_balance:.2f} M$
Change: {self.final_balance - self.initial_balance:+.2f} M$
"""


class ManifoldTrader:
    """Handles trade execution on Manifold Markets."""

    BASE_URL = "https://api.manifold.markets/v0"

    def __init__(self, api_key: str, timeout: int = 30):
        """
        Initialize the trader.

        Args:
            api_key: Manifold Markets API key
        """
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Key {api_key}",
            "Content-Type": "application/json"
        })

    def get_balance(self) -> float:
        """Get current account balance."""
        try:
            response = self.session.get(
                f"{self.BASE_URL}/me",
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json().get('balance', 0.0)
        except requests.RequestException as e:
            logger.error(f"Failed to get balance: {e}")
            return 0.0

    def place_bet(
        self,
        market_id: str,
        outcome: str,
        amount: int,
        limit_prob: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Place a bet on a market.

        Args:
            market_id: Market ID
            outcome: "YES" or "NO"
            amount: Amount in M$
            limit_prob: Optional limit price (0-1)

        Returns:
            API response
        """
        data = {
            "contractId": market_id,
            "outcome": outcome,
            "amount": amount
        }

        if limit_prob is not None:
            data["limitProb"] = limit_prob
            data["expiresMillisAfter"] = 6 * 60 * 60 * 1000  # 6 hours

        response = self.session.post(
            f"{self.BASE_URL}/bet",
            json=data,
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()

    def is_authenticated(self) -> bool:
        """Check if API key is valid."""
        try:
            self.get_balance()
            return True
        except Exception:
            return False


class ArticleTrader:
    """
    Main trading orchestrator - connects articles to trades.

    Pipeline:
    1. Fetch enriched articles from Snowflake
    2. Find relevant prediction markets
    3. Analyze article-market pairs for trading signals
    4. Execute trades on Manifold Markets
    """

    def __init__(
        self,
        manifold_api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        min_edge: float = 0.05,
        min_confidence: float = 0.6,
        max_bet: float = 25.0,
        dry_run: bool = False
    ):
        """
        Initialize the article trader.

        Args:
            manifold_api_key: API key for Manifold Markets (env var MANIFOLD_API_KEY if not provided)
            model: LLM model for analysis
            min_edge: Minimum edge to trade
            min_confidence: Minimum confidence to trade
            max_bet: Maximum bet size
            dry_run: If True, analyze but don't execute trades
        """
        self.manifold_api_key = manifold_api_key or os.getenv("MANIFOLD_API_KEY")
        if not self.manifold_api_key and not dry_run:
            raise ValueError("MANIFOLD_API_KEY required for live trading")

        self.dry_run = dry_run
        self.max_bet = max_bet

        # Initialize components
        self.article_source = SnowflakeArticleSource()
        self.market_matcher = MarketMatcher()
        self.analyzer = ArticleMarketAnalyzer(
            model=model,
            min_edge=min_edge,
            min_confidence=min_confidence,
            max_bet=max_bet
        )

        if not dry_run:
            self.trader = ManifoldTrader(self.manifold_api_key)
        else:
            self.trader = None

        # Track processed articles to avoid duplicates
        self.processed_articles: Set[int] = set()

    def run_session(
        self,
        days: int = 3,
        max_articles: int = 20,
        max_trades: int = 5,
        delay_between_trades: float = 2.0
    ) -> TradingSession:
        """
        Run a complete trading session.

        Args:
            days: How many days back to look for articles
            max_articles: Maximum articles to process
            max_trades: Maximum trades to execute
            delay_between_trades: Delay between trades in seconds

        Returns:
            TradingSession with results
        """
        session = TradingSession(start_time=datetime.now())

        # Get initial balance
        if self.trader:
            session.initial_balance = self.trader.get_balance()
            logger.info(f"Initial balance: {session.initial_balance:.2f} M$")

        try:
            # Step 1: Fetch articles
            logger.info(f"Fetching articles from last {days} days...")
            articles = self.article_source.fetch_recent_articles(
                days=days,
                limit=max_articles,
                min_confidence=0.5,
                market_impact=['high', 'medium']
            )
            session.articles_processed = len(articles)
            logger.info(f"Found {len(articles)} articles to process")

            if not articles:
                logger.info("No articles to process")
                session.end_time = datetime.now()
                return session

            # Step 2: Process each article
            all_signals: List[TradingSignal] = []

            for article in articles:
                if article.id in self.processed_articles:
                    continue

                logger.info(f"\nProcessing article {article.id}: {article.title[:60]}...")

                # Find matching markets
                matches = self.market_matcher.find_markets_for_article(
                    article,
                    max_markets=5
                )
                session.markets_matched += len(matches)

                if not matches:
                    logger.info("  No relevant markets found")
                    continue

                logger.info(f"  Found {len(matches)} potential markets")

                # Analyze each match
                for match in matches:
                    signal = self.analyzer.analyze_match(match)
                    all_signals.append(signal)
                    session.signals_generated += 1

                    if signal.should_trade():
                        logger.info(
                            f"  TRADEABLE: {match.question[:40]}... | "
                            f"{signal.direction.value} @ {signal.edge:+.1%} edge | "
                            f"Conf: {signal.confidence:.0%}"
                        )

                self.processed_articles.add(article.id)

            # Step 3: Filter and execute trades
            tradeable_signals = self.analyzer.filter_tradeable_signals(all_signals)
            logger.info(f"\n{len(tradeable_signals)} tradeable signals from {session.signals_generated} analyzed")

            # Sort by confidence * edge (expected value proxy)
            tradeable_signals.sort(
                key=lambda s: abs(s.edge) * s.confidence,
                reverse=True
            )

            # Execute trades
            trades_made = 0
            for signal in tradeable_signals:
                if trades_made >= max_trades:
                    break

                trade = self._execute_trade(signal)
                session.trades.append(trade)

                if trade.success:
                    session.trades_executed += 1
                    trades_made += 1
                    logger.info(
                        f"TRADE: {signal.direction.value} {trade.amount}M$ on "
                        f"{signal.market_match.question[:40]}..."
                    )
                    time.sleep(delay_between_trades)
                else:
                    session.trades_failed += 1
                    session.errors.append(trade.error or "Unknown error")

        except Exception as e:
            logger.error(f"Session error: {e}")
            session.errors.append(str(e))

        # Final balance
        if self.trader:
            session.final_balance = self.trader.get_balance()

        session.end_time = datetime.now()
        return session

    def _execute_trade(self, signal: TradingSignal) -> Trade:
        """Execute a single trade."""
        outcome = signal.direction.value
        amount = int(min(signal.suggested_bet_size, self.max_bet))

        trade = Trade(
            signal=signal,
            outcome=outcome,
            amount=amount,
            timestamp=datetime.now(),
            success=False
        )

        if self.dry_run:
            logger.info(f"[DRY RUN] Would place {outcome} bet of {amount}M$ on {signal.market_id}")
            trade.success = True
            return trade

        try:
            response = self.trader.place_bet(
                market_id=signal.market_id,
                outcome=outcome,
                amount=amount
            )
            trade.success = True
            trade.bet_response = response
        except Exception as e:
            trade.error = str(e)
            logger.error(f"Trade failed: {e}")

        return trade

    def analyze_article(self, article_id: int) -> List[TradingSignal]:
        """
        Analyze a specific article and return trading signals.

        Useful for testing/debugging individual articles.
        """
        article = self.article_source.fetch_article_by_id(article_id)
        if not article:
            logger.error(f"Article {article_id} not found")
            return []

        matches = self.market_matcher.find_markets_for_article(article, max_markets=10)
        signals = self.analyzer.analyze_matches(matches)
        return signals

    def run_continuous(
        self,
        interval_minutes: int = 60,
        max_trades_per_cycle: int = 3
    ):
        """
        Run continuous trading loop.

        Args:
            interval_minutes: Minutes between cycles
            max_trades_per_cycle: Max trades per cycle
        """
        logger.info(f"Starting continuous trading (interval: {interval_minutes}m)")

        while True:
            try:
                logger.info(f"\n{'='*50}")
                logger.info(f"Starting trading cycle at {datetime.now()}")

                session = self.run_session(
                    days=1,  # Only look at recent articles
                    max_articles=10,
                    max_trades=max_trades_per_cycle
                )

                logger.info(session.summary())

            except KeyboardInterrupt:
                logger.info("Interrupted by user")
                break
            except Exception as e:
                logger.error(f"Cycle error: {e}")

            logger.info(f"Sleeping {interval_minutes} minutes...")
            time.sleep(interval_minutes * 60)
