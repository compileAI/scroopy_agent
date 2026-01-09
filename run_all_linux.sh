#!/bin/bash

# Script to run all main scrapers in sequence
set -e  # Exit on any error

echo "Starting scraper pipeline..."
echo ""

echo "=== Running Stagehand scraper ==="
xvfb-run -a python src/main/stagehand_main.py
echo ""

echo "=== Running Custom scraper ==="
xvfb-run -a python src/main/custom_main.py
echo ""

echo "=== Running RSS scraper ==="
python src/main/rss_main.py
echo ""

echo "=== Running Crawl4AI scraper ==="
python src/main/crawl4ai_main.py
echo ""

echo "✓ All scrapers completed successfully!"
