# Oreacle Bot v2.0

**News-driven prediction market trading** - Connects enriched articles from Snowflake to Manifold Markets, using LLM analysis to find and execute trading opportunities.

## What's New in v2.0

The bot has been completely rebuilt to be a general-purpose article-to-prediction-market trading machine:

- **Article Source**: Pulls enriched news articles from Snowflake (MIKHAIL.PUBLIC.ARTICLE)
- **Market Matching**: Automatically finds relevant Manifold Markets for each article
- **LLM Analysis**: Uses GPT to determine if articles provide tradeable edge
- **Kelly Betting**: Sizes bets using Kelly criterion with configurable risk parameters
- **CLI Interface**: Easy-to-use commands for running, testing, and analyzing

## Quick Start (v2.0)

```bash
# Install
pip install -e .

# Configure credentials (copy .env.example to .env and fill in)
cp .env.example .env

# Test connections
oreaclebot test

# Run in dry-run mode (analyze but don't trade)
oreaclebot run --dry-run

# Run live trading
oreaclebot run --max-trades 3 --max-bet 25
```

## Commands

```bash
# Single trading session
oreaclebot run [options]
  --days N          Days of articles to analyze (default: 3)
  --max-articles N  Max articles to process (default: 20)
  --max-trades N    Max trades to execute (default: 5)
  --min-edge F      Minimum edge to trade (default: 0.05 = 5%)
  --min-confidence F Minimum confidence (default: 0.6 = 60%)
  --max-bet F       Maximum bet size in M$ (default: 25)
  --dry-run         Analyze without trading

# Continuous mode
oreaclebot continuous --interval 60 --max-trades 3

# Analyze specific article
oreaclebot analyze <article_id>

# List recent articles
oreaclebot list --days 7 --limit 20

# Test connections
oreaclebot test
```

## How It Works

```
Snowflake ARTICLE Table
    │
    ▼
┌─────────────────────┐
│ 1. Fetch Articles   │  Recent enriched articles with metal/impact analysis
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ 2. Match Markets    │  Search Manifold for relevant prediction markets
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ 3. LLM Analysis     │  GPT analyzes article-market pairs for edge
└─────────────────────┘
    │
    ▼
┌─────────────────────┐
│ 4. Execute Trades   │  Place bets using Kelly-optimal sizing
└─────────────────────┘
```

## Required Credentials

Set these in `.env` or as environment variables:

```bash
# Snowflake (article source)
SNOWFLAKE_USER=xxx
SNOWFLAKE_PASSWORD=xxx
SNOWFLAKE_ACCOUNT=xxx

# Manifold Markets (trading)
MANIFOLD_API_KEY=xxx

# OpenAI (analysis)
OPENAI_API_KEY=xxx
```

---

# Legacy Mode (v1.0)

The original oreaclebot functionality for monitoring Chinese regulatory sources is still available via `oreaclebot-legacy`.

## Overview (Legacy)

Oreacle-bot v1.0 monitors the exact sources cited in the ["CATL receives license renewal for Yichun Lithium mine by x"](https://manifold.markets/MikhailTal/catl-receives-license-renewal-for-y) prediction market:

- **CNINFO** - Official CATL (300750.SZ) company disclosures
- **SZSE** - Shenzhen Stock Exchange notices  
- **Jiangxi Natural Resources** - Provincial mining rights announcements

The bot uses GPT-4o-mini to analyze Chinese regulatory documents in real-time, extracting exact quotes, translating them, assessing confidence levels, and posting bilingual analysis to Manifold Markets with optional conservative trading.

## Quick Start

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables**
   ```bash
   export MANIFOLD_API_KEY="your_manifold_api_key"
   export MARKET_SLUG="MikhailTal/catl-receives-license-renewal-for-y"
   export OPENAI_API_KEY="your_openai_api_key"  # For LLM analysis
   ```

3. **Run the monitor**

   You can run the bot **either locally or in GitHub Actions** (or both simultaneously):
   
   **Local (Continuous):**
   ```bash
   source .env && python src/monitor.py
   # Runs forever with 15-minute cycles until stopped
   ```
   
   **GitHub Actions (Cloud Automation):**
   ```bash
   # Set up repository secrets, then push to GitHub
   # Automatically runs every 15 minutes in the cloud
   # See GITHUB_ACTIONS_SETUP.md for complete setup guide
   ```

## Configuration

### Required Environment Variables
- `MANIFOLD_API_KEY` - Your Manifold Markets API key
- `MARKET_SLUG` - The market to monitor (e.g., "MikhailTal/catl-receives-license-renewal-for-y")

### LLM Integration (Recommended)
- `OPENAI_API_KEY` - OpenAI API key for GPT-4o-mini analysis
- `OREACLE_MODEL` - OpenAI model to use (default: "gpt-4o-mini")
- `OREACLE_MIN_CONFIDENCE` - Minimum confidence for decisions (default: 0.75)

### Legacy Translation (Optional - LLM handles translation internally)
- `DEEPL_API_KEY` - DeepL API key for translation fallback
- `GOOGLE_TRANSLATE_API_KEY` - Google Translate API key fallback

### Other Settings
- `OREACLE_COMMENT_ONLY` - Set to "1" to disable trading (default: "1")
- `OREACLE_INTERVAL` - Check interval in seconds (default: 900)
- `OREACLE_DB` - SQLite database path (default: "./tmp/oreacle.db")
- `OREACLE_LOG` - Log level: DEBUG, INFO, WARNING, ERROR (default: "INFO")

## Data Sources

### CNINFO (China Securities Information)
- **URL**: https://www.cninfo.com.cn/
- **Purpose**: Official CATL company filings and announcements
- **Keywords**: Chinese terms for mining permits, renewals, production status

### SZSE (Shenzhen Stock Exchange)  
- **URL**: https://www.szse.cn/disclosure/listed/notice/
- **Purpose**: Exchange notices related to CATL (300750.SZ)
- **Scope**: Regulatory notices and company announcements

### Jiangxi Natural Resources Department
- **URLs**: 
  - https://bnr.jiangxi.gov.cn/jxszrzyt/kyqjygggs/kyqjygsg/
  - https://bnr.jiangxi.gov.cn/jxszrzyt/ckqcrgggs/ckqcrgsg/
  - https://www.yichun.gov.cn/ycsrmzf/gytdsyqhkyqcr/
- **Purpose**: Mining rights transactions and permits for Yichun region
- **Focus**: License renewals, exploration permits, production approvals

## Core Functionality

### What the Bot Does
1. **Monitors 3 Chinese regulatory sources** every 15 minutes for CATL lithium mine updates
2. **Analyzes documents with AI** using GPT-4o-mini to extract structured information
3. **Posts bilingual comments** to Manifold Markets with exact Chinese quotes + English translations
4. **Makes conservative trades** only when high-confidence analysis passes strict safety gates
5. **Tracks all activity** in SQLite database to prevent duplicate processing

### Specific Analysis Capabilities
- **Document Classification**: YES_CONDITION (license renewals, production approvals), NO_CONDITION (exploration only, suspensions), AMBIGUOUS, IRRELEVANT
- **Mine Matching**: Identifies references to Jianxiawo/枧下窝 mine specifically vs other locations
- **Authority Recognition**: Maps regulatory bodies (Jiangxi Natural Resources, Yichun authorities, etc.)
- **Confidence Scoring**: 0.0-1.0 confidence with evidence-based reasoning
- **Risk Detection**: Flags exploration-only permits, typos, unclear language
- **Quote Extraction**: Preserves exact Chinese regulatory language with literal English translations

### Trading Logic (Optional)
- **Conservative Gates**: Requires entity match + license action + high confidence + clear evidence
- **NO False Positives**: Multiple validation layers prevent bad trades
- **Small Positions**: Default 5 M$ limit orders at 55% probability
- **Comment-Only Mode**: Trading disabled by default (`OREACLE_COMMENT_ONLY=1`)

## Technical Implementation

### With LLM Integration (Recommended)
1. **Enhanced Data Collection**: 
   - CNINFO: Keyword search + stock code 300750 sweep
   - SZSE: Retry logic with reduced keyword set on failures
   - Jiangxi: Mining rights portal scraping with relevance filtering
2. **Boolean Prefiltering**: Requires (company OR mine OR geo) AND (license-action OR resumption verb)
3. **LLM Analysis**: Structured JSON Schema output with exact quote preservation
4. **Decision Gates**: Conservative logic prevents false positives in trading
5. **Rich Comments**: Bilingual format with confidence indicators, evidence quotes, source links

### Fallback Mode (No OpenAI Key)
- Regex-based classification with Chinese/English keyword matching
- Optional DeepL/Google translation for Chinese text
- Basic relevance filtering and comment generation
- Automatically enabled when `OPENAI_API_KEY` not provided

### Analysis Pipeline
```
Raw Document → Boolean Prefilter → LLM Extraction → Decision Gates → Action
                     ↓                    ↓              ↓
               Entity + Action      Structured JSON    Comment/Trade
               Match Required       with Evidence      if Gates Pass
```

## Architecture & Files

### Core LLM Components
- `src/models.py` - Pydantic schemas for structured LLM outputs
- `src/llm_client.py` - OpenAI client with JSON Schema validation  
- `src/decision.py` - Conservative decision gates for trading safety
- `src/comment_renderer.py` - Rich bilingual comment formatting
- `phrasebook.yml` - Chinese/English term definitions for LLM context

### Legacy Components (Fallback)
- `src/translate.py` - DeepL/Google translation (used when no LLM)
- `src/classify.py` - Regex-based classification (used when no LLM)

### Data Sources & Storage
- `src/sources/cninfo.py` - CATL official filings scraper
- `src/sources/szse.py` - Stock exchange notices scraper  
- `src/sources/jiangxi.py` - Provincial mining authority scraper
- `src/storage.py` - SQLite deduplication database
- `src/client.py` - Manifold Markets API client

### Main Application
- `src/monitor.py` - Main monitoring loop with LLM integration (local continuous)
- `src/monitor_single.py` - Single-cycle version for GitHub Actions (cloud)

## Expected Output Examples

### LLM Analysis Output
When the bot finds a relevant document, it extracts structured information:
```json
{
  "mine_match": "JIANXIAWO_MATCH",
  "proposed_label": "YES_CONDITION", 
  "confidence": 0.85,
  "key_terms_found_zh": ["采矿许可证延续", "恢复生产"],
  "key_terms_found_en": ["mining license renewal", "resume production"],
  "evidence": [{
    "exact_zh_quote": "同意宜春枧下窝锂云母矿采矿许可证延续申请",
    "en_literal": "Approve the mining license renewal application for Yichun Jianxiawo lithium mica mine",
    "where_in_doc": "main announcement"
  }]
}
```

### Manifold Comments
The bot posts bilingual comments like:
```markdown
🤖 Oreacle LLM Analysis — 🟢 Confidence: 85%

📄 Source: [江西省自然资源厅批复](https://example.com/doc)
🏛️ Authority: Jiangxi Natural Resources Department  
⛏️ Mine Match: JIANXIAWO_MATCH

Key Evidence (ZH→EN):
> 中文: 「同意宜春枧下窝锂云母矿采矿许可证延续申请」
> English: Approve the mining license renewal application for Yichun Jianxiawo lithium mica mine

LLM Verdict: YES_CONDITION → Final: YES_CONDITION

Terms Found:
- 🇨🇳 采矿许可证延续, 恢复生产
- 🇬🇧 mining license renewal, resume production

*Automated analysis by Oreacle Bot*
```

### Console Logs
```
[INFO] LLM integration: ENABLED
[INFO] LLM model: gpt-4o-mini, min confidence: 0.75
[INFO] Connected to market: CATL receives license renewal...
[INFO] CNINFO: Found 2 items
[INFO] Processing cninfo item: 宜春枧下窝采矿许可证延续申请获批...
[INFO] Running LLM extraction...
[INFO] LLM Analysis - Proposed: YES_CONDITION, Final: YES_CONDITION, Confidence: 0.85
[INFO] Posted LLM comment for cninfo item_12345
```

## Deployment Options

### Local vs GitHub Actions

You can run the bot in three ways:

1. **Local Only**: Run `python src/monitor.py` on your machine
   - Persistent SQLite database in `./tmp/oreacle.db`
   - Perfect deduplication across runs
   - Requires your machine to stay online

2. **GitHub Actions Only**: Automated cloud execution every 15 minutes
   - Database resets each run (ephemeral runners)
   - Still works perfectly for regulatory monitoring
   - No machine uptime requirements

3. **Both Simultaneously**: Local + GitHub Actions running in parallel
   - Redundancy ensures no missed announcements
   - Each maintains its own deduplication state
   - Maximum reliability

### Why Non-Persistent Database Works Fine

**GitHub Actions resets the SQLite database each run, but this doesn't cause problems because:**

1. **Regulatory announcements are rare** - New CATL mining documents appear maybe 1-10 times per month
2. **Quick re-analysis is cheap** - GPT-4o-mini costs ~$0.01 per document, so re-analyzing the same document a few times costs pennies
3. **Manifold prevents spam** - If you post the same comment twice, Manifold will reject duplicates
4. **Time-based filtering** - Most regulatory sources show recent items first, so old items naturally age out
5. **Short analysis window** - Each run only takes 2-3 minutes, so the overlap window is minimal

**In practice:** A new regulatory announcement might get analyzed 2-3 times total before it's no longer in the "recent items" feed from the sources. This costs ~$0.03 instead of ~$0.01 - negligible for the reliability benefits of cloud automation.

### Production Recommendation

**Use GitHub Actions for production** because:
- ✅ 24/7 uptime without your laptop
- ✅ Exact 15-minute intervals 
- ✅ Built-in monitoring and logs
- ✅ Free hosting (GitHub Actions)
- ✅ Redundant with occasional re-analysis (~$0.02 extra cost per document)

**Use Local for development** because:
- ✅ Perfect deduplication
- ✅ Immediate feedback and debugging
- ✅ No CI/CD setup required

## Relevant Links

- [Target Manifold Market](https://manifold.markets/MikhailTal/catl-receives-license-renewal-for-y) - The prediction market being monitored
- [CNINFO Portal](https://www.cninfo.com.cn/) - CATL official filings
- [SZSE Disclosure Portal](https://www.szse.cn/disclosure/listed/notice/) - Stock exchange notices
- [Jiangxi Natural Resources](https://bnr.jiangxi.gov.cn/) - Provincial mining authority