#!/usr/bin/env python3
"""
Unified scraper main entry point.
Runs all scraping methods (RSS, Reddit, Crawl4AI) and writes results to Supabase.
"""
import asyncio
import sys
import logging
from pathlib import Path
from typing import List
from datetime import datetime

# Ensure src is on path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from scrapers.custom.rss_scraper import run as run_rss_scraper
from scrapers.custom.reddit import run_async as run_reddit_scraper_async
from scrapers.crawl4ai.extract_articles import run as run_crawl4ai_scraper
from utils.supabase import upsert_source_articles
from models.source_article import SourceArticle

logger = logging.getLogger(__name__)


def print_batch_summary(all_articles: List[SourceArticle], results: dict, start_time: datetime):
    """Print a comprehensive summary of batch processing results."""
    total_time = (datetime.now() - start_time).total_seconds()
    
    logger.info(f"\n{'='*60}")
    logger.info("📊 UNIFIED SCRAPER BATCH SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"RSS Articles: {results['rss']['count']} (Status: {results['rss']['status']})")
    logger.info(f"Reddit Articles: {results['reddit']['count']} (Status: {results['reddit']['status']})")
    logger.info(f"Crawl4AI Articles: {results['crawl4ai']['count']} (Status: {results['crawl4ai']['status']})")
    logger.info(f"Total Articles Collected: {len(all_articles)}")
    logger.info(f"Total Processing Time: {total_time:.1f}s")
    
    if len(all_articles) > 0:
        avg_time = total_time / len(all_articles)
        logger.info(f"Average Time Per Article: {avg_time:.2f}s")
    
    # Print sample articles
    if all_articles:
        logger.info(f"\n✅ Sample Articles (first 3):")
        for i, article in enumerate(all_articles[:3], start=1):
            logger.info(f"{i}. {article.title[:60]}...")
            logger.info(f"   📅 {article.published}")
            logger.info(f"   🏷️  Source ID: {article.source_id}")
    
    # Print any errors
    errors = [result for result in results.values() if result['status'] == 'error']
    if errors:
        logger.warning(f"\n❌ Errors encountered:")
        for method, result in results.items():
            if result['status'] == 'error':
                logger.warning(f"  - {method.upper()}: {result.get('error', 'Unknown error')}")


async def run_all_scrapers(limit: int = None) -> List[SourceArticle]:
    """Run all scraping methods and collect SourceArticle records."""
    logger.info("🧩 Running all scrapers...")
    all_articles: List[SourceArticle] = []
    results = {}
    
    # 1. RSS Scraper
    try:
        logger.info("\n📰 Running RSS scraper...")
        rss_articles = run_rss_scraper(limit=limit)
        all_articles.extend(rss_articles)
        results['rss'] = {'count': len(rss_articles), 'status': 'success'}
        logger.info(f"✅ RSS: collected {len(rss_articles)} articles")
    except Exception as e:
        logger.error(f"❌ Error in RSS scraper: {e}")
        results['rss'] = {'count': 0, 'status': 'error', 'error': str(e)}
    
    # 2. Reddit Scraper
    try:
        logger.info("\n📱 Running Reddit scraper...")
        reddit_articles = await run_reddit_scraper_async(limit=limit)
        all_articles.extend(reddit_articles)
        results['reddit'] = {'count': len(reddit_articles), 'status': 'success'}
        logger.info(f"✅ Reddit: collected {len(reddit_articles)} articles")
    except Exception as e:
        logger.error(f"❌ Error in Reddit scraper: {e}")
        results['reddit'] = {'count': 0, 'status': 'error', 'error': str(e)}
    
    # 3. Crawl4AI Scraper
    try:
        logger.info("\n🕷️ Running Crawl4AI scraper...")
        crawl4ai_articles = await run_crawl4ai_scraper(limit=limit)
        all_articles.extend(crawl4ai_articles)
        results['crawl4ai'] = {'count': len(crawl4ai_articles), 'status': 'success'}
        logger.info(f"✅ Crawl4AI: collected {len(crawl4ai_articles)} articles")
    except Exception as e:
        logger.error(f"❌ Error in Crawl4AI scraper: {e}")
        results['crawl4ai'] = {'count': 0, 'status': 'error', 'error': str(e)}
    
    return all_articles, results


async def main_async(limit: int = None, dry_run: bool = False):
    """Async main function for unified scraper."""
    start_time = datetime.now()
    logger.info("🚀 Starting unified scraper batch processing")
    
    try:
        # Run all scrapers
        all_articles, results = await run_all_scrapers(limit=limit)
        
        # Print comprehensive summary
        print_batch_summary(all_articles, results, start_time)
        
        if dry_run:
            logger.info(f"\n🔎 Dry run: would write {len(all_articles)} articles to database")
            return
        
        if not all_articles:
            logger.warning("\n⚠️  No articles to write")
            return
        
        # Write to Supabase
        logger.info(f"\n💾 Writing {len(all_articles)} articles to Supabase...")
        written = upsert_source_articles(all_articles)
        logger.info(f"✅ Done. Upserted {written} of {len(all_articles)} records")
        
    except Exception as e:
        logger.error(f"❌ Fatal error in unified scraper: {e}")
        sys.exit(1)


def main():
    """Main entry point for unified scrapers."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run all scrapers and write to Supabase")
    parser.add_argument("--limit", type=int, help="Limit items per scraper (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to Supabase; just print summary")
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    asyncio.run(main_async(limit=args.limit, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
