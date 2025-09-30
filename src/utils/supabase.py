import hashlib
import os
from typing import Dict, Any, List, Set, Optional
import logging
from datetime import datetime, timezone, timedelta

from supabase import create_client, Client

# Import models with relative paths from the new structure
import sys
from pathlib import Path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from models.source_article import SourceArticle
from models.stagehand import Article
from models.news_sources import NewsSource, RssSource, RedditSource, CrawlSource
from utils.date_utils import safe_parse_date

logger = logging.getLogger(__name__)


def get_supabase_client() -> Client:
    """Get Supabase client with proper error handling"""
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables required")
    
    return create_client(supabase_url, supabase_key)


async def get_stagehand_sources() -> List[Dict[str, Any]]:
    """Get all sources from stagehand_sources table"""
    try:
        supabase = get_supabase_client()
        
        # Get all stagehand sources with their master_sources info
        response = supabase.table('stagehand_sources').select(
            '*, master_sources(name, url, scrape_method)'
        ).execute()
        
        if not response.data:
            print("📭 No stagehand sources found in database")
            return []
        
        print(f"📖 Found {len(response.data)} stagehand sources")
        return response.data
        
    except Exception as e:
        print(f"❌ Error fetching stagehand sources: {e}")
        return []


async def write_article_to_db(article: Article, source_id: int, url: str) -> bool:
    """Write extracted article to source_articles table (legacy Stagehand format)"""
    try:
        supabase = get_supabase_client()
        
        # Prepare article data for database
        article_data = {
            'source_id': source_id,
            'url': url,
            'title': article.title,
            'author': article.author,
            'content': '\n\n'.join(article.content) if article.content else '',
            'published': article.date_published.isoformat() if article.date_published else None,
            'id': f"{source_id}_{hashlib.md5(url.encode()).hexdigest()[:16]}"  # Generate unique ID
        }
        
        # Check if article already exists
        existing = supabase.table('source_articles').select('id').eq('id', article_data['id']).execute()
        
        if existing.data:
            print(f"🔄 Article already exists in database: {article.title[:50]}...")
            return True
        
        # Insert new article
        result = supabase.table('source_articles').insert(article_data).execute()
        
        if result.data:
            print(f"✅ Successfully wrote article to database: {article.title[:50]}...")
            return True
        else:
            print(f"❌ Failed to write article to database: {article.title[:50]}...")
            return False
            
    except Exception as e:
        print(f"❌ Error writing article to database: {e}")
        return False


def add_source_to_database(source_url: str, source_name: str) -> bool:
    """Add a new source to the database."""
    try:
        supabase = get_supabase_client()
        
        # First, insert into master_sources table
        master_source_data = {
            "url": source_url,
            "name": source_name,
            "scrape_method": "stagehand",
            "active": True
        }
        
        master_result = supabase.table("master_sources").insert(master_source_data).execute()
        
        if not master_result.data:
            print("Error: Failed to insert into master_sources table")
            return False
        
        # Get the auto-assigned ID from the inserted record
        master_source_id = master_result.data[0]["id"]
        
        # Insert into stagehand_sources table
        stagehand_source_data = {
            "id": master_source_id,
            "name": source_name,
            "home_url": source_url
        }
        
        stagehand_result = supabase.table("stagehand_sources").insert(stagehand_source_data).execute()
        
        if not stagehand_result.data:
            print("Error: Failed to insert into stagehand_sources table")
            return False
        
        print(f"Successfully added source '{source_name}' to database with ID: {master_source_id}")
        return True
        
    except Exception as e:
        print(f"Database error: {str(e)}")
        return False


# =============================================================================
# SCRAPING-SPECIFIC DATABASE FUNCTIONS (PORTED FROM COMPILE)
# =============================================================================


def get_active_rss_sources() -> List[RssSource]:
    """Get all active RSS sources from the database."""
    try:
        supabase = get_supabase_client()
        result = supabase.table('rss_news_sources')\
            .select('name, rss_url, home_url, source_id, created_at, master_sources!inner(active)')\
            .eq('master_sources.active', True)\
            .execute()
        
        # Extract only the RSS source fields, ignoring the master_sources join data
        rss_sources = []
        for row in result.data:
            rss_data = {
                'name': row['name'],
                'rss_url': row['rss_url'], 
                'home_url': row['home_url'],
                'source_id': row['source_id'],
                'created_at': row['created_at']
            }
            rss_sources.append(RssSource(**rss_data))
        
        logger.info(f"Found {len(rss_sources)} active RSS sources")
        return rss_sources
    except Exception as e:
        logger.error(f'Error fetching active RSS sources: {e}')
        return []


def get_active_reddit_sources() -> List[RedditSource]:
    """Get all active Reddit sources from the database."""
    try:
        supabase = get_supabase_client()
        result = supabase.table('reddit_sources')\
            .select('subreddit, flairs, source_id, created_at, master_sources!inner(name, url, active)')\
            .eq('master_sources.active', True)\
            .execute()
        
        reddit_sources = []
        for row in result.data:
            reddit_data = {
                'name': row['master_sources']['name'],
                'subreddit': row['subreddit'],
                'home_url': row['master_sources']['url'], 
                'flairs': row['flairs'],
                'source_id': row['source_id'],
                'created_at': row['created_at'],
            }
            reddit_sources.append(RedditSource(**reddit_data))
        
        logger.info(f"Found {len(reddit_sources)} active Reddit sources")
        return reddit_sources
    except Exception as e:
        logger.error(f'Error fetching active Reddit sources: {e}')
        return []


async def query_crawl_source_by_url(url: str) -> Optional[CrawlSource]:
    """Queries Supabase for a crawl source by home_url."""
    try:
        supabase = get_supabase_client()
        response = supabase.table("crawl_sources").select("*").eq("home_url", url).execute()
        
        if response.data and len(response.data) > 0:
            source_data = response.data[0]
            return CrawlSource(**source_data)

        return None
    except Exception as e:
        logger.error(f"Error querying crawl source by URL: {e}")
        return None


def get_active_crawl_sources() -> List[CrawlSource]:
    """Retrieves all active crawl sources from the crawl_sources table."""
    try:
        supabase = get_supabase_client()
        response = supabase.table("crawl_sources")\
            .select('name, home_url, source_id, created_at, link_schema, article_schema, master_sources!inner(active)')\
            .eq('master_sources.active', True)\
            .execute()
        
        if not response.data:
            logger.info("No active crawl sources found in database")
            return []
            
        # Extract only the crawl source fields, ignoring the master_sources join data
        crawl_sources = []
        for row in response.data:
            crawl_data = {
                'name': row['name'],
                'home_url': row['home_url'],
                'source_id': row['source_id'],
                'created_at': row['created_at'],
                'link_schema': row['link_schema'],
                'article_schema': row['article_schema']
            }
            crawl_sources.append(CrawlSource(**crawl_data))
            
        logger.info(f"Retrieved {len(crawl_sources)} active crawl sources from database")
        return crawl_sources
    except Exception as e:
        logger.error(f"Error retrieving active crawl sources: {e}")
        return []


async def insert_crawl_source(crawl_source: CrawlSource) -> Optional[CrawlSource]:
    """Inserts a CrawlSource into master_sources and crawl_sources tables."""
    try:
        supabase = get_supabase_client()
        
        # Insert into master_sources first
        master_response = supabase.table("master_sources").insert({
            "name": crawl_source.name,
            "url": crawl_source.home_url,
            "scrape_method": "crawl"
        }).execute()

        if not master_response.data or len(master_response.data) == 0:
            logger.error("Failed to insert into master_sources")
            return None

        master_source = master_response.data[0]
        source_id = master_source["id"]
        created_at = master_source["created_at"]

        logger.info(f"Inserted into master_sources with id {source_id}")

        # Insert into crawl_sources
        crawl_response = supabase.table("crawl_sources").insert({
            "source_id": source_id,
            "link_schema": crawl_source.link_schema,
            "article_schema": crawl_source.article_schema,
            "home_url": crawl_source.home_url,
            "name": crawl_source.name,
        }).execute()

        if not crawl_response.data or len(crawl_response.data) == 0:
            logger.error("Failed to insert into crawl_sources")
            return None

        logger.info("Successfully inserted crawl source linked to master source")

        # Return updated CrawlSource object
        updated_crawl_source = CrawlSource(
            name=crawl_source.name,
            home_url=crawl_source.home_url,
            source_id=source_id,
            created_at=safe_parse_date(created_at) or datetime.now(timezone.utc),  # parse ISO string into datetime
            link_schema=crawl_source.link_schema,
            article_schema=crawl_source.article_schema,
        )

        return updated_crawl_source
    except Exception as e:
        logger.error(f"Failed to insert new crawl source: {e}")
        return None


def get_existing_article_urls_by_source(source_id: int, days_back: int = 30) -> Set[str]:
    """Get a set of existing article URLs for a specific source within the recent time window."""
    try:
        supabase = get_supabase_client()
        
        # Calculate the cutoff date
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
        
        response = supabase.table('source_articles')\
            .select('url')\
            .eq('source_id', source_id)\
            .gte('published', cutoff_date)\
            .execute()
        
        urls = {row['url'] for row in response.data if row.get('url')}
        logger.info(f"Found {len(urls)} existing URLs for source {source_id} (last {days_back} days)")
        return urls
    except Exception as e:
        logger.error(f'Error fetching existing URLs for source {source_id}: {e}')
        return set()


def upsert_source_articles(articles: List[SourceArticle]) -> List[SourceArticle]:
    """
    Inserts new articles into the Supabase database using SourceArticle objects.
    Returns a list of articles that were actually inserted (new articles only).
    """
    # First, deduplicate articles within this batch by ID
    seen_ids = set()
    unique_articles = []
    duplicates_removed = 0
    
    for article in articles:
        if article.id not in seen_ids:
            seen_ids.add(article.id)
            unique_articles.append(article)
        else:
            duplicates_removed += 1
    
    if duplicates_removed > 0:
        logger.info(f"Removed {duplicates_removed} duplicate articles from batch (same title/source)")
        logger.info(f"Processing {len(unique_articles)} unique articles out of {len(articles)} total")
    
    articles_data = [article.to_db_dict() for article in unique_articles]
    
    try:
        supabase = get_supabase_client()
        
        # Use upsert with on_conflict to handle duplicates
        response = supabase.table('source_articles').upsert(
            articles_data, 
            on_conflict='id',
            count='exact'
        ).execute()
        
        # Count tells us how many were actually inserted
        inserted_count = response.count
        
        if inserted_count > 0:
            logger.info(f"Inserted {inserted_count} new articles out of {len(unique_articles)} unique")
            # Return the articles that were actually inserted
            # Since we can't easily determine which specific ones, 
            # we'll return all for now (this is conservative)
            return unique_articles[:inserted_count] if inserted_count < len(unique_articles) else unique_articles
        else:
            logger.info(f"No new articles inserted (all {len(unique_articles)} were duplicates)")
            return []
            
    except Exception as e:
        logger.error(f"Error inserting articles: {e}")
        logger.error(f"   Original batch: {len(articles)} articles")
        logger.error(f"   After deduplication: {len(unique_articles)} articles")
        return []