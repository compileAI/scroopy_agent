#!/usr/bin/env python3
"""
Custom scrapers orchestrator.

Runs all custom scrapers and writes results to Supabase.
"""

import asyncio
import sys
from pathlib import Path
from typing import List

# Ensure src is on path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from models.source_article import SourceArticle
from scrapers.custom import hf_daily_papers, reddit


def run_all_custom_scrapers(limit: int = None) -> List[SourceArticle]:
    """Run all custom scrapers and collect SourceArticle records.
    
    Args:
        limit: Optional limit on records per scraper
        
    Returns:
        List of SourceArticle records from all scrapers
    """
    print("🧩 Running all custom scrapers...")
    records: List[SourceArticle] = []
    
    # Add new scrapers here as they're created
    scrapers = [
        ("HF Daily Papers", hf_daily_papers.run),
        ("Reddit", reddit.run),
    ]
    
    for name, scraper_func in scrapers:
        try:
            print(f"\n📡 Running {name} scraper...")
            scraper_records = scraper_func(limit=limit)
            records.extend(scraper_records)
            print(f"✅ {name}: collected {len(scraper_records)} records")
        except Exception as e:
            print(f"❌ Error in {name} scraper: {e}")
    
    return records


def print_summary(articles: List[SourceArticle], limit_preview: int = 5):
    """Print a summary of collected articles."""
    print(f"\n📦 Collected {len(articles)} SourceArticle records total")
    
    if not articles:
        return
    
    print(f"\n📋 Preview (first {min(limit_preview, len(articles))}):")
    for i, art in enumerate(articles[:limit_preview], start=1):
        print(f"\n{i}. {art.title}")
        print(f"   👥 {art.author}")
        print(f"   📅 {art.published}")
        print(f"   🏷️  source_id: {art.source_id}")
        print(f"   🔗 {art.url}")
        content_preview = art.content[:150] + "..." if len(art.content) > 150 else art.content
        print(f"   📝 {content_preview}")


async def main():
    """Main entry point for custom scrapers."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run all custom scrapers and write to Supabase")
    # BUG: I think this limit propagates in a weird way and will cause a bug in the future
    parser.add_argument("--limit", type=int, default=20, help="Limit items per scraper (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to Supabase; just print summary")
    parser.add_argument("--preview", type=int, default=5, help="Number of items to preview")
    args = parser.parse_args()
    
    # Run scrapers
    articles = run_all_custom_scrapers(limit=args.limit)
    
    # Print summary
    print_summary(articles, limit_preview=args.preview)
    
    if args.dry_run:
        print("\n🔎 Dry run: skipping Supabase write")
        return
    
    if not articles:
        print("\n⚠️  No articles to write")
        return
    
    # Write to Supabase
    print("\n💾 Writing to Supabase...")
    try:
        from utils.supabase import write_source_articles_to_db
        from utils.pinecone import process_and_write_to_pinecone
        written = write_source_articles_to_db(articles)
        await process_and_write_to_pinecone(articles)
        print(f"✅ Done. Upserted {written} of {len(articles)} records")
    except Exception as e:
        print(f"❌ Error writing to Supabase: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())