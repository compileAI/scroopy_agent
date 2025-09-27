#!/usr/bin/env python3
"""
Reddit scraper main entry point.
Processes all configured Reddit sources and writes results to Supabase.
"""
import asyncio
import sys
import logging
from pathlib import Path
from typing import Optional

# Ensure src is on path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from scrapers.custom.reddit import run as run_reddit_scraper, run_async as run_reddit_scraper_async
from utils.supabase import upsert_source_articles
from models.source_article import SourceArticle

logger = logging.getLogger(__name__)


def print_summary(articles: list[SourceArticle], limit_preview: int = 5):
    """Print a summary of collected articles."""
    logger.info(f"📦 Collected {len(articles)} SourceArticle records total")
    
    if not articles:
        return
    
    logger.info(f"📋 Preview (first {min(limit_preview, len(articles))}):")
    for i, art in enumerate(articles[:limit_preview], start=1):
        logger.info(f"{i}. {art.title}")
        logger.info(f"   👥 {art.author}")
        logger.info(f"   📅 {art.published}")
        logger.info(f"   🏷️  source_id: {art.source_id}")
        logger.info(f"   🔗 {art.url}")
        content_preview = art.content[:150] + "..." if len(art.content) > 150 else art.content
        logger.info(f"   📝 {content_preview}")


async def main_async(limit: Optional[int] = None, dry_run: bool = False, preview: int = 5):
    """Async main function for Reddit scraper."""
    logger.info("🚀 Starting Reddit scraper batch processing (async)")
    
    try:
        # Run Reddit scraper
        articles = await run_reddit_scraper_async(limit=limit)
        
        # Print summary
        print_summary(articles, limit_preview=preview)
        
        if dry_run:
            logger.info("🔎 Dry run: skipping Supabase write")
            return
        
        if not articles:
            logger.warning("⚠️  No articles to write")
            return
        
        # Write to Supabase
        logger.info("💾 Writing to Supabase...")
        written = upsert_source_articles(articles)
        logger.info(f"✅ Done. Upserted {written} of {len(articles)} records")
        
    except Exception as e:
        logger.error(f"❌ Error in Reddit scraper: {e}")
        sys.exit(1)


def main_sync(limit: Optional[int] = None, dry_run: bool = False, preview: int = 5):
    """Sync main function for Reddit scraper."""
    logger.info("🚀 Starting Reddit scraper batch processing (sync)")
    
    try:
        # Run Reddit scraper
        articles = run_reddit_scraper(limit=limit)
        
        # Print summary
        print_summary(articles, limit_preview=preview)
        
        if dry_run:
            logger.info("🔎 Dry run: skipping Supabase write")
            return
        
        if not articles:
            logger.warning("⚠️  No articles to write")
            return
        
        # Write to Supabase
        logger.info("💾 Writing to Supabase...")
        written = upsert_source_articles(articles)
        logger.info(f"✅ Done. Upserted {written} of {len(articles)} records")
        
    except Exception as e:
        logger.error(f"❌ Error in Reddit scraper: {e}")
        sys.exit(1)


def main():
    """Main entry point for Reddit scrapers."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Reddit scrapers and write to Supabase")
    parser.add_argument("--limit", type=int, help="Limit items per source (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to Supabase; just print summary")
    parser.add_argument("--preview", type=int, default=5, help="Number of items to preview")
    parser.add_argument("--sync", action="store_true", help="Use synchronous version (fallback)")
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if args.sync:
        main_sync(limit=args.limit, dry_run=args.dry_run, preview=args.preview)
    else:
        asyncio.run(main_async(limit=args.limit, dry_run=args.dry_run, preview=args.preview))


if __name__ == "__main__":
    main()
