#!/usr/bin/env python3
"""
Stagehand batch processor.

Processes all configured Stagehand sources and writes results to Supabase.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime

# Ensure src is on path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from utils.supabase import get_stagehand_sources, write_source_articles_to_db
from scrapers.stagehand.extract import process_sources_batch
from models.source_article import SourceArticle


def print_batch_summary(results, start_time: datetime):
    """Print a summary of batch processing results."""
    # Calculate statistics
    total_time = (datetime.now() - start_time).total_seconds()
    
    # Handle mixed result types (legacy dict format vs SourceArticle)
    source_articles = [r for r in results if isinstance(r, SourceArticle)]
    legacy_results = [r for r in results if isinstance(r, dict)]
    
    successful_legacy = sum(1 for r in legacy_results if r.get('status') == 'success')
    skipped_legacy = sum(1 for r in legacy_results if r.get('status') == 'skipped')
    failed_legacy = sum(1 for r in legacy_results if r.get('status') == 'failed')
    
    total_sources = len(results)
    total_successful = len(source_articles) + successful_legacy
    
    print(f"\n{'='*60}")
    print("📊 STAGEHAND BATCH SUMMARY")
    print(f"{'='*60}")
    print(f"Total sources processed: {total_sources}")
    print(f"Successfully extracted: {total_successful}")
    print(f"  └─ As SourceArticles: {len(source_articles)}")
    print(f"  └─ Legacy format: {successful_legacy}")
    if skipped_legacy > 0:
        print(f"Skipped (cache hits): {skipped_legacy}")
    if failed_legacy > 0:
        print(f"Failed: {failed_legacy}")
    
    if total_sources > 0:
        success_rate = (total_successful / total_sources) * 100
        print(f"Success rate: {success_rate:.1f}%")
    
    print(f"Total processing time: {total_time:.1f}s")
    
    if total_sources > 0:
        avg_time = total_time / total_sources
        print(f"Average time per source: {avg_time:.1f}s")
    
    # Print failed sources
    if failed_legacy > 0:
        print(f"\n❌ Failed sources:")
        for result in legacy_results:
            if result.get('status') == 'failed':
                print(f"  - {result.get('source_name', 'Unknown')}: {result.get('error', 'Unknown error')}")
    
    # Print successful extractions preview
    if source_articles:
        print(f"\n✅ SourceArticle extractions:")
        for article in source_articles[:3]:  # Show first 3
            print(f"  - {article.title[:60]}...")


async def main(batch_size: int = 5, max_sources: Optional[int] = None, dry_run: bool = False):
    """Main function for Stagehand batch processing."""
    
    print("🤖 Starting Stagehand batch processing")
    
    # Get all sources from database
    sources = await get_stagehand_sources()
    
    if not sources:
        print("❌ No Stagehand sources found. Exiting.")
        return
    
    # Limit sources if specified
    if max_sources:
        sources = sources[:max_sources]
        print(f"📊 Limited to {max_sources} sources for testing")
    
    print(f"📊 Total sources to process: {len(sources)}")
    print(f"📦 Batch size: {batch_size}")
    
    start_time = datetime.now()
    
    try:
        # Process sources in batches, converting to SourceArticles
        results = await process_sources_batch(
            sources, 
            batch_size=batch_size, 
            convert_to_source_articles=True
        )
        
        # Print summary
        print_batch_summary(results, start_time)
        
        # Filter to SourceArticles for DB writing
        source_articles = [r for r in results if isinstance(r, SourceArticle)]
        
        if dry_run:
            print(f"\n🔎 Dry run: would write {len(source_articles)} SourceArticles to database")
            return
        
        if source_articles:
            print(f"\n💾 Writing {len(source_articles)} SourceArticles to database...")
            written = write_source_articles_to_db(source_articles)
            print(f"✅ Upserted {written} records to database")
        else:
            print("\n⚠️  No SourceArticles to write to database")
        
    except Exception as e:
        print(f"💥 Fatal error during processing: {e}")
        sys.exit(1)


def cli_main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Stagehand batch article extraction')
    parser.add_argument('--batch-size', type=int, default=5, help='Number of sources to process in each batch')
    parser.add_argument('--max-sources', type=int, help='Maximum number of sources to process (for testing)')
    parser.add_argument('--dry-run', action='store_true', help='Do not write to database; just process and show summary')
    
    args = parser.parse_args()
    
    asyncio.run(main(
        batch_size=args.batch_size, 
        max_sources=args.max_sources,
        dry_run=args.dry_run
    ))


if __name__ == "__main__":
    cli_main()