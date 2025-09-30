#!/usr/bin/env python3
"""
RSS scraper main entry point.
Processes all configured RSS sources and writes results to Supabase.
"""
import asyncio
import sys
import logging
from pathlib import Path

# Ensure src is on path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from scrapers.rss.rss_scraper import run as run_rss_scraper
from utils.supabase import upsert_source_articles
from models.source_article import SourceArticle
from utils.pinecone import process_and_write_to_pinecone

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


async def main():
    """Main entry point for RSS scrapers."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run RSS scrapers and write to Supabase")
    parser.add_argument("--limit", type=int, help="Limit items per source (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to Supabase; just print summary")
    parser.add_argument("--preview", type=int, default=5, help="Number of items to preview")
    args = parser.parse_args()
    
    
    logger.info("🚀 Starting RSS scraper batch processing")
    
    try:
        # Run RSS scraper
        articles = run_rss_scraper(limit=args.limit)
        
        # Print summary
        print_summary(articles, limit_preview=args.preview)
        
        if args.dry_run:
            logger.info("🔎 Dry run: skipping Supabase write")
            return
        
        if not articles:
            logger.warning("⚠️  No articles to write")
            return
        
        # Write to Supabase
        logger.info("💾 Writing to Supabase...")
        written = upsert_source_articles(articles)
        await process_and_write_to_pinecone(articles)
        logger.info(f"✅ Done. Upserted {written} of {len(articles)} records")
        
    except Exception as e:
        logger.error(f"❌ Error in RSS scraper: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
