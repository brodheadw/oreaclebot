"""
Article-Market Analyzer - Uses LLM to determine if an article provides trading edge.

Given an article and a market, this analyzer determines:
1. Whether the article is relevant to the market
2. What direction the article suggests (YES/NO probability shift)
3. How confident we should be in this signal
4. What bet size is appropriate
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Literal
from enum import Enum

from openai import OpenAI

from .snowflake_source import Article
from .market_matcher import MarketMatch

logger = logging.getLogger(__name__)


class Direction(str, Enum):
    """Trading direction."""
    YES = "YES"
    NO = "NO"
    SKIP = "SKIP"


@dataclass
class TradingSignal:
    """A trading signal derived from article-market analysis."""
    article: Article
    market_match: MarketMatch
    direction: Direction
    probability_estimate: float  # Our estimate of true probability
    confidence: float  # How confident we are in this estimate
    reasoning: str
    suggested_bet_size: float  # Suggested bet in M$
    edge: float  # Estimated edge (our prob - market prob)

    @property
    def market_id(self) -> str:
        return self.market_match.market_id

    @property
    def current_probability(self) -> float:
        return self.market_match.probability

    def should_trade(self, min_edge: float = 0.05, min_confidence: float = 0.6) -> bool:
        """Check if signal meets trading thresholds."""
        if self.direction == Direction.SKIP:
            return False
        if abs(self.edge) < min_edge:
            return False
        if self.confidence < min_confidence:
            return False
        return True


# JSON Schema for structured LLM output
ANALYSIS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "is_relevant": {
            "type": "boolean",
            "description": "Whether the article is relevant to the market question"
        },
        "relevance_explanation": {
            "type": "string",
            "description": "Brief explanation of how article relates to market"
        },
        "direction": {
            "type": "string",
            "enum": ["YES", "NO", "SKIP"],
            "description": "Whether article suggests YES, NO, or no tradeable signal"
        },
        "probability_estimate": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Your estimate of the true probability (0.0 to 1.0)"
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "How confident you are in your probability estimate (0.0 to 1.0)"
        },
        "reasoning": {
            "type": "string",
            "description": "Detailed reasoning for your probability estimate"
        },
        "key_evidence": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Key pieces of evidence from the article"
        }
    },
    "required": [
        "is_relevant", "relevance_explanation", "direction",
        "probability_estimate", "confidence", "reasoning", "key_evidence"
    ]
}


ANALYSIS_SYSTEM_PROMPT = """You are an expert market analyst evaluating whether news articles provide tradeable signals for prediction markets.

Your job is to:
1. Determine if the article is relevant to the market question
2. Estimate the TRUE probability of the market question based on ALL available information including this article
3. Compare your estimate to the current market price to identify mispricing
4. Only recommend trading if you have genuine confidence in your probability estimate

Key principles:
- Be skeptical of articles that seem sensationalized or have unclear sources
- Consider base rates and how much weight to give to individual news items
- Remember that markets are often efficient - you need strong evidence to believe you know better
- A "high impact" article about palladium supply doesn't automatically mean all palladium markets should move
- Consider timing: does the article's information align with the market's timeframe?

Output Format:
- is_relevant: Does this article have ANY bearing on the market question?
- direction: YES if article suggests higher probability, NO if lower, SKIP if uncertain or irrelevant
- probability_estimate: Your best estimate of TRUE probability (not how much to adjust from current)
- confidence: How confident are you? 0.5 = uncertain, 0.7 = somewhat confident, 0.9 = very confident
- reasoning: Clear explanation of your logic

Remember: Markets are hard to beat. Only suggest trades when you have genuine edge."""


def get_openai_client() -> OpenAI:
    """Get OpenAI client."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    return OpenAI(api_key=api_key)


class ArticleMarketAnalyzer:
    """
    Uses LLM to analyze article-market pairs and generate trading signals.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        min_edge: float = 0.05,
        min_confidence: float = 0.6,
        max_bet: float = 50.0,
        kelly_fraction: float = 0.25
    ):
        """
        Initialize the analyzer.

        Args:
            model: OpenAI model to use
            min_edge: Minimum probability edge to consider trading
            min_confidence: Minimum confidence to consider trading
            max_bet: Maximum bet size in M$
            kelly_fraction: Fraction of Kelly criterion to use for bet sizing
        """
        self.model = model
        self.min_edge = min_edge
        self.min_confidence = min_confidence
        self.max_bet = max_bet
        self.kelly_fraction = kelly_fraction
        self.client = get_openai_client()

    def analyze_match(self, match: MarketMatch) -> TradingSignal:
        """
        Analyze an article-market match and generate a trading signal.

        Args:
            match: MarketMatch containing article and market

        Returns:
            TradingSignal with trading recommendation
        """
        article = match.article
        market = match.market

        # Build the analysis prompt
        user_prompt = self._build_prompt(article, market, match)

        try:
            # Call LLM with structured output
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "MarketAnalysis",
                        "strict": True,
                        "schema": ANALYSIS_SCHEMA
                    }
                },
                messages=[
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ]
            )

            content = response.choices[0].message.content
            analysis = json.loads(content)

            return self._build_signal(match, analysis)

        except Exception as e:
            logger.error(f"Analysis failed for article {article.id}: {e}")
            return TradingSignal(
                article=article,
                market_match=match,
                direction=Direction.SKIP,
                probability_estimate=match.probability,
                confidence=0.0,
                reasoning=f"Analysis error: {str(e)}",
                suggested_bet_size=0.0,
                edge=0.0
            )

    def _build_prompt(self, article: Article, market: Dict[str, Any], match: MarketMatch) -> str:
        """Build the analysis prompt."""
        # Truncate body if too long
        body = article.body[:3000] if article.body else "No body available"

        prompt = f"""
ARTICLE INFORMATION:
Title: {article.title}
Date: {article.article_date}
Source: {article.source}
Metal/Commodity: {article.metal or 'Unknown'}
Pre-analyzed Impact: {article.market_impact or 'Unknown'}
Pre-analyzed Confidence: {article.confidence or 'Unknown'}
Impact Mechanism: {article.impact_mechanism or 'Not specified'}
Detailed Analysis: {article.detailed_analysis or 'Not available'}

Article Body:
{body}

---

MARKET INFORMATION:
Question: {market.get('question', 'Unknown')}
Current Probability: {market.get('probability', 0.5):.1%}
Description: {market.get('description', 'No description')[:500]}
Close Time: {market.get('closeTime', 'Unknown')}
Creator: {market.get('creatorUsername', 'Unknown')}

Match Reason: {match.match_reason}
Match Relevance Score: {match.relevance_score:.2f}

---

TASK:
Analyze whether this article provides a tradeable signal for this market.
Consider:
1. Is the article actually relevant to what the market is asking?
2. What is your best estimate of the true probability?
3. How confident are you in this estimate?
4. Is there enough edge vs the current market price to trade?

Be rigorous and skeptical. Only recommend trading with genuine conviction.
"""
        return prompt

    def _build_signal(self, match: MarketMatch, analysis: Dict[str, Any]) -> TradingSignal:
        """Build a TradingSignal from LLM analysis."""
        article = match.article
        current_prob = match.probability
        our_prob = analysis['probability_estimate']
        confidence = analysis['confidence']
        direction_str = analysis['direction']

        # Calculate edge
        edge = our_prob - current_prob

        # Determine direction
        if direction_str == "YES":
            direction = Direction.YES
        elif direction_str == "NO":
            direction = Direction.NO
        else:
            direction = Direction.SKIP

        # Calculate bet size using Kelly criterion
        bet_size = self._calculate_bet_size(current_prob, our_prob, confidence)

        return TradingSignal(
            article=article,
            market_match=match,
            direction=direction,
            probability_estimate=our_prob,
            confidence=confidence,
            reasoning=analysis['reasoning'],
            suggested_bet_size=bet_size,
            edge=edge
        )

    def _calculate_bet_size(
        self,
        market_prob: float,
        our_prob: float,
        confidence: float
    ) -> float:
        """
        Calculate bet size using Kelly criterion.

        Kelly formula: f* = (bp - q) / b
        where:
        - b = odds received
        - p = probability of winning
        - q = probability of losing

        We use a fraction of Kelly for safety.
        """
        if our_prob <= 0 or our_prob >= 1 or market_prob <= 0 or market_prob >= 1:
            return 0.0

        # Determine if we're betting YES or NO
        if our_prob > market_prob:
            # Betting YES
            # We pay market_prob, we win (1 - market_prob) if YES
            p = our_prob
            b = (1 - market_prob) / market_prob
        else:
            # Betting NO
            # We pay (1 - market_prob), we win market_prob if NO
            p = 1 - our_prob
            b = market_prob / (1 - market_prob)

        q = 1 - p

        # Kelly formula
        kelly_fraction_optimal = (b * p - q) / b if b > 0 else 0

        if kelly_fraction_optimal <= 0:
            return 0.0

        # Apply our conservative fraction and confidence scaling
        bet_fraction = kelly_fraction_optimal * self.kelly_fraction * confidence

        # Convert to M$ (assume 1000 M$ bankroll for sizing)
        bet_size = bet_fraction * 1000

        # Apply constraints
        bet_size = max(1.0, min(bet_size, self.max_bet))

        return bet_size

    def analyze_matches(self, matches: List[MarketMatch]) -> List[TradingSignal]:
        """
        Analyze multiple matches and return signals.

        Args:
            matches: List of MarketMatch objects

        Returns:
            List of TradingSignal objects
        """
        signals = []
        for match in matches:
            signal = self.analyze_match(match)
            signals.append(signal)
            logger.info(
                f"Analyzed: {match.question[:40]}... | "
                f"Direction: {signal.direction.value} | "
                f"Edge: {signal.edge:+.1%} | "
                f"Confidence: {signal.confidence:.1%}"
            )
        return signals

    def filter_tradeable_signals(self, signals: List[TradingSignal]) -> List[TradingSignal]:
        """Filter signals to only those worth trading."""
        tradeable = [
            s for s in signals
            if s.should_trade(min_edge=self.min_edge, min_confidence=self.min_confidence)
        ]
        return tradeable
