"""
Article Trader CLI - Command-line interface for article-driven trading.

Usage:
    python -m oreaclebot.article_trader [command] [options]

Commands:
    run         Run a single trading session
    continuous  Run continuous trading loop
    analyze     Analyze a specific article
    test        Test connections and configuration
"""

import argparse
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def cmd_run(args):
    """Run a single trading session."""
    from .trader import ArticleTrader

    logger.info("Article Trader - Single Session")
    logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE TRADING'}")
    logger.info(f"Model: {args.model}")
    logger.info(f"Max articles: {args.max_articles}")
    logger.info(f"Max trades: {args.max_trades}")
    logger.info(f"Min edge: {args.min_edge:.0%}")
    logger.info(f"Min confidence: {args.min_confidence:.0%}")

    trader = ArticleTrader(
        model=args.model,
        min_edge=args.min_edge,
        min_confidence=args.min_confidence,
        max_bet=args.max_bet,
        dry_run=args.dry_run
    )

    session = trader.run_session(
        days=args.days,
        max_articles=args.max_articles,
        max_trades=args.max_trades
    )

    print(session.summary())

    # Print trade details
    if session.trades:
        print("\nTrade Details:")
        print("-" * 60)
        for trade in session.trades:
            status = "OK" if trade.success else "FAILED"
            print(
                f"  [{status}] {trade.outcome} {trade.amount}M$ | "
                f"Edge: {trade.signal.edge:+.1%} | "
                f"{trade.signal.market_match.question[:40]}..."
            )

    if session.errors:
        print(f"\nErrors ({len(session.errors)}):")
        for error in session.errors[:5]:
            print(f"  - {error}")


def cmd_continuous(args):
    """Run continuous trading loop."""
    from .trader import ArticleTrader

    logger.info("Article Trader - Continuous Mode")
    logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE TRADING'}")
    logger.info(f"Interval: {args.interval} minutes")

    trader = ArticleTrader(
        model=args.model,
        min_edge=args.min_edge,
        min_confidence=args.min_confidence,
        max_bet=args.max_bet,
        dry_run=args.dry_run
    )

    trader.run_continuous(
        interval_minutes=args.interval,
        max_trades_per_cycle=args.max_trades
    )


def cmd_analyze(args):
    """Analyze a specific article."""
    from .trader import ArticleTrader

    logger.info(f"Analyzing article ID: {args.article_id}")

    trader = ArticleTrader(
        model=args.model,
        min_edge=args.min_edge,
        min_confidence=args.min_confidence,
        dry_run=True  # Never trade in analyze mode
    )

    signals = trader.analyze_article(args.article_id)

    if not signals:
        print("No trading signals found for this article")
        return

    print(f"\nFound {len(signals)} potential signals:\n")
    print("-" * 80)

    for i, signal in enumerate(signals, 1):
        tradeable = "TRADEABLE" if signal.should_trade() else "SKIP"
        print(f"\n{i}. [{tradeable}] {signal.market_match.question[:60]}...")
        print(f"   Direction: {signal.direction.value}")
        print(f"   Current market prob: {signal.current_probability:.1%}")
        print(f"   Our estimate: {signal.probability_estimate:.1%}")
        print(f"   Edge: {signal.edge:+.1%}")
        print(f"   Confidence: {signal.confidence:.0%}")
        print(f"   Suggested bet: {signal.suggested_bet_size:.0f} M$")
        print(f"   Reasoning: {signal.reasoning[:200]}...")


def cmd_test(args):
    """Test connections and configuration."""
    print("Testing Article Trader Configuration\n")
    print("=" * 50)

    # Test environment variables
    print("\n1. Environment Variables:")
    env_vars = [
        ("SNOWFLAKE_USER", os.getenv("SNOWFLAKE_USER")),
        ("SNOWFLAKE_PASSWORD", "***" if os.getenv("SNOWFLAKE_PASSWORD") else None),
        ("SNOWFLAKE_ACCOUNT", os.getenv("SNOWFLAKE_ACCOUNT")),
        ("MANIFOLD_API_KEY", "***" if os.getenv("MANIFOLD_API_KEY") else None),
        ("OPENAI_API_KEY", "***" if os.getenv("OPENAI_API_KEY") else None),
    ]
    for name, value in env_vars:
        status = "OK" if value else "MISSING"
        print(f"   {name}: {status}")

    # Test Snowflake connection
    print("\n2. Snowflake Connection:")
    try:
        from .snowflake_source import SnowflakeArticleSource, test_connection

        if test_connection():
            print("   Snowflake: CONNECTED")

            # Test article fetch
            source = SnowflakeArticleSource()
            articles = source.fetch_recent_articles(days=1, limit=5)
            print(f"   Recent articles (1 day): {len(articles)}")
        else:
            print("   Snowflake: FAILED")
    except Exception as e:
        print(f"   Snowflake: ERROR - {e}")

    # Test Manifold connection
    print("\n3. Manifold Markets:")
    try:
        from .market_matcher import ManifoldSearchClient

        client = ManifoldSearchClient()
        markets = client.search_markets("palladium", limit=3)
        print(f"   Search test: Found {len(markets)} markets for 'palladium'")

        if os.getenv("MANIFOLD_API_KEY"):
            from .trader import ManifoldTrader

            trader = ManifoldTrader(os.getenv("MANIFOLD_API_KEY"))
            balance = trader.get_balance()
            print(f"   Authenticated: YES")
            print(f"   Balance: {balance:.2f} M$")
        else:
            print("   Authenticated: NO (no API key)")
    except Exception as e:
        print(f"   Manifold: ERROR - {e}")

    # Test OpenAI
    print("\n4. OpenAI API:")
    try:
        from openai import OpenAI

        client = OpenAI()
        # Just test that we can create a client
        print("   OpenAI: CONFIGURED")
    except Exception as e:
        print(f"   OpenAI: ERROR - {e}")

    print("\n" + "=" * 50)
    print("Test complete!")


def cmd_list_articles(args):
    """List recent articles."""
    from .snowflake_source import SnowflakeArticleSource

    source = SnowflakeArticleSource()
    articles = source.fetch_recent_articles(
        days=args.days,
        limit=args.limit,
        min_confidence=0.3,
        market_impact=['high', 'medium', 'low']
    )

    print(f"\nRecent Articles (last {args.days} days):\n")
    print("-" * 80)

    for article in articles:
        impact = article.market_impact or "?"
        conf = f"{article.confidence:.0%}" if article.confidence else "?"
        metal = article.metal or "?"
        print(f"\n[{article.id}] {article.title[:70]}...")
        print(f"    Date: {article.article_date} | Metal: {metal} | Impact: {impact} | Conf: {conf}")

    print(f"\nTotal: {len(articles)} articles")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Article Trader - News-driven prediction market trading",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run a single trading session")
    run_parser.add_argument("--days", type=int, default=3, help="Days of articles to analyze")
    run_parser.add_argument("--max-articles", type=int, default=20, help="Maximum articles to process")
    run_parser.add_argument("--max-trades", type=int, default=5, help="Maximum trades to execute")
    run_parser.add_argument("--min-edge", type=float, default=0.05, help="Minimum edge to trade (0.05 = 5%%)")
    run_parser.add_argument("--min-confidence", type=float, default=0.6, help="Minimum confidence (0.6 = 60%%)")
    run_parser.add_argument("--max-bet", type=float, default=25.0, help="Maximum bet size in M$")
    run_parser.add_argument("--model", default="gpt-4o-mini", help="LLM model for analysis")
    run_parser.add_argument("--dry-run", action="store_true", help="Analyze without executing trades")
    run_parser.set_defaults(func=cmd_run)

    # Continuous command
    cont_parser = subparsers.add_parser("continuous", help="Run continuous trading loop")
    cont_parser.add_argument("--interval", type=int, default=60, help="Minutes between cycles")
    cont_parser.add_argument("--max-trades", type=int, default=3, help="Max trades per cycle")
    cont_parser.add_argument("--min-edge", type=float, default=0.05, help="Minimum edge to trade")
    cont_parser.add_argument("--min-confidence", type=float, default=0.6, help="Minimum confidence")
    cont_parser.add_argument("--max-bet", type=float, default=25.0, help="Maximum bet size")
    cont_parser.add_argument("--model", default="gpt-4o-mini", help="LLM model")
    cont_parser.add_argument("--dry-run", action="store_true", help="Analyze without trading")
    cont_parser.set_defaults(func=cmd_continuous)

    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a specific article")
    analyze_parser.add_argument("article_id", type=int, help="Article ID to analyze")
    analyze_parser.add_argument("--min-edge", type=float, default=0.05)
    analyze_parser.add_argument("--min-confidence", type=float, default=0.6)
    analyze_parser.add_argument("--model", default="gpt-4o-mini")
    analyze_parser.set_defaults(func=cmd_analyze)

    # Test command
    test_parser = subparsers.add_parser("test", help="Test connections")
    test_parser.set_defaults(func=cmd_test)

    # List articles command
    list_parser = subparsers.add_parser("list", help="List recent articles")
    list_parser.add_argument("--days", type=int, default=7, help="Days to look back")
    list_parser.add_argument("--limit", type=int, default=20, help="Max articles to show")
    list_parser.set_defaults(func=cmd_list_articles)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        args.func(args)
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 1
    except Exception as e:
        logger.error(f"Error: {e}")
        if os.getenv("DEBUG"):
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
