"""
RSS feed scraper
Fetches articles from RSS feeds and converts them to SourceArticle objects.
"""
import feedparser
import time
import logging
from datetime import datetime, timezone
from typing import List

import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from models.source_article import SourceArticle
from models.news_sources import RssSource

logger = logging.getLogger(__name__)


def get_rss_source_name(url: str) -> str:
    """Get the name of an RSS feed from its URL."""
    try:
        feed = feedparser.parse(url)
        if getattr(feed, "status", 200) == 200:
            if hasattr(feed.feed, 'title'):
                return feed.feed.title
        return None
    except Exception as e:
        logger.error(f"Error getting RSS source name from {url}: {e}")
        return None


def fetch_articles_from_rss(news_sources: List[RssSource]) -> List[SourceArticle]:
    """
    Fetch articles from RSS sources and convert to SourceArticle objects.
    
    Args:
        news_sources: List of RssSource objects to scrape
        
    Returns:
        List of SourceArticle objects
    """
    articles = []
    
    for source in news_sources:
        logger.info(f"📰 Fetching RSS feed: {source.name}")
        
        try:
            feed = feedparser.parse(source.rss_url)
            
            if getattr(feed, "status", 200) != 200:
                logger.error(f'Failed to get RSS feed for {source.name}. Status code: {getattr(feed, "status", "unknown")}')
                continue
                
            logger.info(f"Parsing {len(feed.entries)} articles from {source.name}")
            
            for entry in feed.entries:
                try:
                    # Extract fields with fallbacks
                    published = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        published = datetime.fromtimestamp(
                            time.mktime(entry.published_parsed), 
                            tz=timezone.utc
                        )
                    
                    # Build content from available fields
                    content = ""
                    if hasattr(entry, 'content') and entry.content:
                        content = entry.content[0].value
                    elif hasattr(entry, 'summary'):
                        content = entry.summary
                    
                    # If we have both summary and content, combine them
                    if hasattr(entry, 'summary') and hasattr(entry, 'content') and entry.content:
                        content = f"Summary: {entry.summary}\n\nContent: {entry.content[0].value}"
                    elif hasattr(entry, 'summary') and not content:
                        content = f"Summary: {entry.summary}"
                    
                    # Create SourceArticle
                    article = SourceArticle(
                        published=published,
                        title=getattr(entry, 'title', ''),
                        content=content,
                        author=getattr(entry, 'author', ''),
                        source_id=source.source_id,
                        url=getattr(entry, 'link', '')
                    )
                    
                    articles.append(article)
                    
                except Exception as e:
                    logger.error(f"Error processing RSS entry from {source.name}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f'Error fetching RSS feed for {source.name}: {e}')
            continue
    
    logger.info(f"📰 RSS scraping complete: {len(articles)} articles collected")
    return articles


def run(limit: int = None) -> List[SourceArticle]:
    """
    Main entry point for RSS scraper.
    
    Args:
        limit: Optional limit on number of articles to return
        
    Returns:
        List of SourceArticle objects
    """
    from utils.supabase import get_active_rss_sources
    
    logger.info("🚀 Starting RSS scraper")
    
    # Get active RSS sources from database
    rss_sources = get_active_rss_sources()
    
    if not rss_sources:
        logger.warning("No active RSS sources found")
        return []
    
    # Fetch articles from all sources
    articles = fetch_articles_from_rss(rss_sources)
    
    # Apply limit if specified
    if limit and len(articles) > limit:
        articles = articles[:limit]
        logger.info(f"✂️ Limited results to {limit} articles")
    
    logger.info(f"✅ RSS scraper completed: {len(articles)} articles")
    return articles


if __name__ == "__main__":
    # For testing the scraper directly
    import argparse
    
    parser = argparse.ArgumentParser(description="RSS Feed Scraper")
    parser.add_argument("--limit", type=int, help="Limit number of articles")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to database")
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    articles = run(limit=args.limit)
    
    if args.dry_run:
        logger.info(f"🔎 Dry run: would write {len(articles)} articles to database")
    else:
        from utils.supabase import upsert_source_articles
        inserted = upsert_source_articles(articles)
        logger.info(f"💾 Inserted {len(inserted)} new articles to database")
