# SCROOPY AGENT

A modular web scraping system that collects articles from multiple sources using different scraping methods. All scrapers output a common `SourceArticle` format that gets written to Supabase.

## Architecture

The system is organized into **General Methods** (each in their own directory) and **Site-Specific Methods** (grouped in `/custom/`):

```
src/
├── main/                     # Entry points
│   ├── custom_main.py        # Run all site-specific scrapers
│   ├── rss_main.py          # Run RSS feed scraper
│   ├── crawl4ai_main.py     # Run Crawl4AI scraper
│   └── stagehand_main.py    # Run Stagehand scraper
├── scrapers/                 # Scraping strategies
│   ├── rss/                 # RSS feed scraping (GENERAL)
│   │   └── rss_scraper.py
│   ├── custom/              # Site-specific scrapers (CUSTOM)
│   │   ├── hf_daily_papers.py  # HuggingFace papers
│   │   └── reddit.py           # Reddit posts
│   ├── crawl4ai/           # AI-powered web scraping (GENERAL)
│   │   ├── extract_articles.py
│   │   ├── llm_fallback.py
│   │   └── schema_generation.py
│   └── stagehand/          # Browser automation (GENERAL)
│       ├── client.py
│       └── extract.py
├── models/                  # Data models
│   └── source_article.py   # Common output format
└── utils/                   # Shared utilities
    ├── supabase.py         # Database operations
    ├── http.py             # HTTP session management
    ├── settings.py         # Configuration
    ├── logging.py          # Logging setup
    └── ids.py              # ID generation
```

### Scraping Methods

**General Methods** (broad scraping techniques):
- **RSS**: Parse RSS/Atom feeds from news sites
- **Crawl4AI**: AI-powered content extraction from web pages
- **Stagehand**: Browser automation for dynamic content

**Site-Specific Methods** (custom scrapers for individual platforms):
- **HuggingFace Daily Papers**: Academic papers from HuggingFace
- **Reddit**: Posts and discussions from configured subreddits

## Usage

### Site-Specific Scrapers (Custom)

Run all site-specific scrapers (HuggingFace + Reddit):

```bash
# Dry run (no database writes)
python3 src/main/custom_main.py --limit 10 --dry-run

# Write to database
python3 src/main/custom_main.py --limit 50

# Full run with all available articles
python3 src/main/custom_main.py
```

### RSS Feed Scraper

Process RSS feeds configured in your Supabase database:

```bash
# Dry run
python3 src/main/rss_main.py --limit 20 --dry-run

# Write to database
python3 src/main/rss_main.py --limit 50

# Process all configured RSS sources
python3 src/main/rss_main.py
```

### Crawl4AI Scraper

AI-powered content extraction from web pages:

```bash
# Dry run
python3 src/main/crawl4ai_main.py --limit 10 --dry-run

# Process configured sources
python3 src/main/crawl4ai_main.py
```

### Stagehand Browser Automation

Process sources using browser automation:

```bash
# Dry run
python3 src/main/stagehand_main.py --batch-size 5 --max-sources 10 --dry-run

# Process all configured sources
python3 src/main/stagehand_main.py --batch-size 5

# Test with limited sources
python3 src/main/stagehand_main.py --batch-size 3 --max-sources 5
```