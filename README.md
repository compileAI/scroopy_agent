# SCROOPY NON-AGENT
- refactored so that scraping logic goes into /scrapers, orchestration into main
- currently we only have stagehand and hf papers in here, need to add c4ai stuff

All scrapers output a common `SourceArticle` format that gets written to Supabase.

## Architecture

```
src/
├── main/                   # Entry points
│   ├── custom_main.py      # Run all custom scrapers
│   └── stagehand_main.py   # Run Stagehand batch processing
├── scrapers/               # Scraping strategies
│   ├── custom/             # Purpose-built scrapers
│   │   └── hf_daily_papers.py
│   └── stagehand/          # Browser automation
│       ├── client.py       # Stagehand client wrapper
│       └── extract.py      # Extraction logic
├── models/                 # Data models
│   └── source_article.py   # Common output format
└── utils/                  # Shared utilities
    ├── supabase.py         # Database operations
    ├── http.py             # HTTP session management
    ├── settings.py         # Configuration
    ├── logging.py          # Logging setup
    └── ids.py              # ID generation
```

## Usage

### Custom Scrapers

Run all custom scrapers and write results to Supabase:

```bash
# Dry run (no database writes)
python3 src/main/custom_main.py --limit 10 --dry-run

# Write to database
python3 src/main/custom_main.py --limit 50

# Full run with all available articles
python3 src/main/custom_main.py
```

### Stagehand Strategy

Process sources configured in your Supabase database:

```bash
# Dry run
python3 src/main/stagehand_main.py --batch-size 5 --max-sources 10 --dry-run

# Process all configured sources
python3 src/main/stagehand_main.py --batch-size 5

# Test with limited sources
python3 src/main/stagehand_main.py --batch-size 3 --max-sources 5
```