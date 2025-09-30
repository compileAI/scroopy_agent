"""
Main crawl4ai article extraction - ported from compile for scroopy_agent.
Extracts articles from web sources using crawl4ai with schema-based extraction and LLM fallback.
"""
import logging
from urllib.parse import urljoin
from datetime import datetime, timezone
from typing import List, Optional
from dotenv import load_dotenv

import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from models.source_article import SourceArticle
from models.news_sources import CrawlSource, NewsSource
from .schema_generation import generate_link_schema, generate_article_schema
from .llm_fallback import extract_article_with_llm
from utils.date_utils import safe_parse_date

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


async def extract_articles(crawler, source: NewsSource) -> List[SourceArticle]:
    """
    Extracts articles from a given news source using web scraping.
    
    This function handles both new and existing sources:
    1. For existing sources: Uses stored schemas to extract articles
    2. For new sources: Generates new schemas and stores them in the database
    
    Process:
    1. Checks if source exists in database
    2. Crawls homepage to get HTML content
    3. Uses or generates link schema to find article URLs
    4. Uses or generates article schema to extract article content
    5. Processes and cleans extracted content
    6. Returns list of SourceArticle objects
    
    Args:
        crawler: AsyncWebCrawler instance for making HTTP requests
        source: The news source to extract articles from
    
    Returns:
        List[SourceArticle]: List of extracted articles
    """
    from utils.supabase import query_crawl_source_by_url, insert_crawl_source, get_existing_article_urls_by_source
    
    try:
        from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
    except ImportError:
        logger.error("crawl4ai not installed - article extraction unavailable")
        return []
    
    # Check if this source already exists in our database
    existing_source = await query_crawl_source_by_url(source.home_url)
    
    # Crawl the homepage to get initial HTML content
    logger.info(f"🕷️ Crawling homepage: {source.home_url}")
    result = await crawler.arun(source.home_url)
    if not result.success:
        logger.error(f"Failed to crawl {source.home_url}: {result.error_message}")
        return []

    # If source exists, use its stored schemas for extraction
    if existing_source:
        logger.info("✅ Found existing CrawlSource in database")
        link_schema = existing_source.link_schema
        article_schema = existing_source.article_schema

        # Extract article links using the stored link schema
        link_extraction_strategy = JsonCssExtractionStrategy(link_schema)
        extracted_links = link_extraction_strategy.extract(
            url=source.home_url,
            html_content=result.html,
        )
        
        # Convert relative URLs to absolute URLs
        article_urls = clean_urls(source.home_url, extracted_links)
        logger.info(f"Extracted {len(article_urls)} article URLs")

    # If source is new, generate new schemas
    else:
        logger.info("🔍 No existing source found. Generating schemas...")
        
        # Generate a schema for finding article links
        link_schema = generate_link_schema(page_html=result)
        if not link_schema:
            logger.error("Failed to generate link schema")
            return []
            
        logger.info("Generated link schema successfully")

        # Extract article links using the new schema
        link_extraction_strategy = JsonCssExtractionStrategy(link_schema)
        extracted_links = link_extraction_strategy.extract(
            url=source.home_url,
            html_content=result.html,
        )

        # Convert relative URLs to absolute URLs
        article_urls = clean_urls(source.home_url, extracted_links)
        logger.info(f"Extracted {len(article_urls)} article URLs")

        # Generate a schema for extracting article content
        # Using first 3 articles as examples to learn the content structure
        article_schema = await generate_article_schema(article_urls[:3], crawler)
        if not article_schema:
            logger.error("Failed to generate article schema")
            return []
            
        logger.info("Generated article schema successfully")

        # Create a new CrawlSource object with the generated schemas
        new_crawl_source = CrawlSource(
            name=source.name,
            home_url=source.home_url,
            source_id=-1,  # Will be replaced by database once master_source entry is created
            created_at=datetime.utcnow(),
            link_schema=link_schema,
            article_schema=article_schema,
        )
        
        # Store the new source in the database
        existing_source = await insert_crawl_source(new_crawl_source)
        if not existing_source:
            logger.error("Failed to store new crawl source")
            existing_source = new_crawl_source

    # Filter out URLs that already exist in the database to avoid re-scraping
    logger.info(f"🔍 Filtering existing URLs for source {source.name}...")
    existing_urls = get_existing_article_urls_by_source(existing_source.source_id, days_back=180)
    new_article_urls = [url for url in article_urls if url not in existing_urls]
    
    # Log filtering results
    logger.info(f"📊 URL Filtering Results:")
    logger.info(f"   📋 Total URLs found: {len(article_urls)}")
    logger.info(f"   ✅ New URLs to scrape: {len(new_article_urls)}")
    logger.info(f"   ⏭️  URLs already in DB: {len(article_urls) - len(new_article_urls)}")
    
    if len(new_article_urls) == 0:
        logger.info("ℹ️ No new articles to scrape - all URLs already exist in database")
        return []

    # Set up the extraction strategy using the article schema
    article_extraction_strategy = JsonCssExtractionStrategy(article_schema)
    extracted_articles = []
    failed_extractions = []  # Track failures for potential source alert
    schema_failures = []  # Track articles that failed schema extraction (even if LLM succeeded)
    
    # Process each new article URL (limited to 50 to avoid overloading)
    urls_to_process = new_article_urls[:50]
    logger.info(f"🚀 Processing {len(urls_to_process)} new articles...")
    
    for article_url in urls_to_process:
        result = await _extract_single_article_with_fallback(
            crawler, 
            article_url, 
            article_extraction_strategy, 
            source, 
            existing_source
        )
        
        if result['article']:
            extracted_articles.append(result['article'])
        else:
            failed_extractions.append(article_url)
            
        # Track schema failures regardless of LLM success
        if not result['schema_success']:
            schema_failures.append(article_url)
    
    # Log overall extraction results
    total_attempted = len(urls_to_process)
    total_succeeded = len(extracted_articles)
    total_failed = len(failed_extractions)
    schema_succeeded = total_attempted - len(schema_failures)
    
    logger.info(f"📊 Extraction Results for {source.name}:")
    logger.info(f"   ✅ Total Successful: {total_succeeded}/{total_attempted}")
    logger.info(f"   📋 Schema Successful: {schema_succeeded}/{total_attempted}")
    logger.info(f"   🤖 LLM Fallback Used: {len(schema_failures) - total_failed}/{total_attempted}")
    logger.info(f"   ❌ Complete Failures: {total_failed}/{total_attempted}")
    
    # Log schema failure alert if ALL articles failed SCHEMA extraction
    if total_attempted > 0 and schema_succeeded == 0:
        _log_schema_failure_alert(source, schema_failures, urls_to_process, total_succeeded)
    
    return extracted_articles


async def _extract_single_article_with_fallback(
    crawler, 
    article_url: str, 
    article_extraction_strategy,
    source: NewsSource,
    existing_source: CrawlSource
) -> dict:
    """
    Extract a single article with schema-based extraction and LLM fallback.
    
    Args:
        crawler: AsyncWebCrawler instance
        article_url: URL of the article to extract
        article_extraction_strategy: Schema-based extraction strategy
        source: Original NewsSource object
        existing_source: CrawlSource object with schema information
        
    Returns:
        Dict with 'article' (SourceArticle object or None) and 'schema_success' (bool)
    """
    schema_error = None
    
    try:
        # First attempt: Schema-based extraction
        logger.debug(f"   🔍 Extracting with schema: {article_url}")
        
        # Fetch the article page
        result = await crawler.arun(article_url)
        if not result.success:
            schema_error = f"Failed to crawl page: {result.error_message}"
            logger.debug(f"      ❌ {schema_error}")
        else:
            # Try schema extraction
            extracted_article = article_extraction_strategy.extract(
                url=article_url,
                html_content=result.html,
            )[0]  # it returns a list with only one element
            
            # Validate extracted content
            if not extracted_article or len(extracted_article) == 0:
                schema_error = "Schema extraction returned empty result"
                logger.debug(f"      ❌ {schema_error}")
            else:
                # Process the extracted content
                if "content" in extracted_article and isinstance(extracted_article["content"], list):
                    # Join all text elements with newlines for readability
                    extracted_article["full_content"] = "\n\n".join([p.get("text", "") for p in extracted_article["content"]])
                    extracted_article["content"] = extracted_article["full_content"]
                    del extracted_article["full_content"]
                
                # Validate we have meaningful content
                title = extracted_article.get("title", "").strip()
                content = extracted_article.get("content", "").strip()
                
                if not title or not content or len(content) < 50:
                    schema_error = f"Schema extraction insufficient: title={bool(title)}, content_len={len(content)}"
                    logger.debug(f"      ❌ {schema_error}")
                else:
                    # Schema extraction successful!
                    logger.debug(f"      ✅ Schema extraction successful")
                    
                    # Parse the publication date, defaulting to current time if not found
                    published_date = safe_parse_date(extracted_article.get("date_published", "").split("●")[0].strip())
                    if published_date is None:
                        published_date = datetime.now(timezone.utc)
                    
                    # Create and return SourceArticle object
                    article = SourceArticle(
                        published=published_date,
                        title=title,
                        content=content,
                        author=extracted_article.get("author", ""),
                        source_id=existing_source.source_id,
                        url=article_url
                    )
                    return {'article': article, 'schema_success': True}
                    
    except Exception as e:
        schema_error = f"Schema extraction exception: {str(e)}"
        logger.debug(f"      ❌ {schema_error}")
    
    # Schema extraction failed, try LLM fallback
    logger.debug(f"      🤖 Falling back to LLM extraction...")
    
    try:
        llm_article = await extract_article_with_llm(crawler, article_url, source)
        
        if llm_article:
            # Log successful LLM fallback
            _log_llm_fallback_success(source.name, article_url, schema_error)
            return {'article': llm_article, 'schema_success': False}
        else:
            # Log failed LLM fallback
            _log_llm_fallback_failure(source.name, article_url, schema_error)
            return {'article': None, 'schema_success': False}
            
    except Exception as e:
        # Log LLM exception
        _log_llm_fallback_failure(source.name, article_url, schema_error, str(e))
        return {'article': None, 'schema_success': False}


def clean_urls(base_url: str, extracted_items: List[dict], url_field: str = "article_url") -> List[str]:
    """
    Completes relative URLs into absolute URLs based on the base URL.
    
    Args:
        base_url: The base URL of the site (e.g., 'https://example.com')
        extracted_items: List of extracted dictionaries containing article URLs
        url_field: The field name in each dict that holds the URL
        
    Returns:
        List of completed absolute URLs
    """
    completed_urls = []
    for item in extracted_items:
        url = item.get(url_field)

        # Skip blank, empty, or slash-only URLs
        if not url or url.strip() in {"", "/"}:
            continue

        # Complete relative URLs
        full_url = urljoin(base_url, url.strip())
        completed_urls.append(full_url)
    
    return completed_urls




def _log_llm_fallback_success(source_name: str, article_url: str, schema_error: str):
    """Log successful LLM fallback extraction."""
    logger.info(f"✅ LLM FALLBACK SUCCESS:")
    logger.info(f"   🏷️  Source: {source_name}")
    logger.info(f"   🔗 URL: {article_url}")
    logger.info(f"   📋 Schema Error: {schema_error}")
    logger.info(f"   🤖 LLM Status: SUCCESS")


def _log_llm_fallback_failure(source_name: str, article_url: str, schema_error: str, llm_error: str = "LLM extraction returned None"):
    """Log failed LLM fallback extraction."""
    logger.error(f"❌ LLM FALLBACK FAILURE:")
    logger.error(f"   🏷️  Source: {source_name}")
    logger.error(f"   🔗 URL: {article_url}")
    logger.error(f"   📋 Schema Error: {schema_error}")
    logger.error(f"   🤖 LLM Error: {llm_error}")


def _log_schema_failure_alert(source: NewsSource, schema_failed_urls: List[str], attempted_urls: List[str], total_succeeded: int):
    """
    Log schema failure alert when ALL articles from a source fail schema extraction.
    
    Args:
        source: NewsSource with schema issues
        schema_failed_urls: List of URLs that failed schema extraction
        attempted_urls: List of all URLs that were attempted  
        total_succeeded: Number of articles that succeeded overall (via LLM)
    """
    try:
        # Determine if LLM saved the day
        llm_saved_count = total_succeeded
        status_emoji = "⚠️" if llm_saved_count > 0 else "🚨"
        
        logger.warning(f"{status_emoji} SCHEMA EXTRACTION FAILURE: {source.name}")
        logger.warning(f"SOURCE DETAILS:")
        logger.warning(f"- Name: {source.name}")
        logger.warning(f"- URL: {source.home_url}")
        logger.warning(f"- Total Articles Attempted: {len(attempted_urls)}")
        logger.warning(f"- Schema Extractions Failed: {len(schema_failed_urls)}")
        logger.warning(f"- LLM Fallback Succeeded: {llm_saved_count}")
        logger.warning(f"- Complete Failures: {len(attempted_urls) - total_succeeded}")
        
        status = "LLM fallback rescued the articles" if llm_saved_count > 0 else "CRITICAL - All extractions failed"
        logger.warning(f"STATUS: {status}")
        
        urgency = "Medium - LLM is covering for now, but schema needs updating" if llm_saved_count > 0 else "HIGH - Source is completely broken"
        logger.warning(f"URGENCY: {urgency}")
        
        logger.warning("RECOMMENDED ACTIONS:")
        logger.warning("1. 🔧 UPDATE THE EXTRACTION SCHEMA - The website structure has likely changed")
        logger.warning("2. 🔍 Check the website manually to see what changed")
        logger.warning("3. 🧪 Test the new schema with a few articles before deploying")
        logger.warning("4. 📊 Review crawl logs for specific error patterns")
        
    except Exception as e:
        logger.error(f"Failed to log schema failure alert: {e}")


async def run(limit: int = None) -> List[SourceArticle]:
    """
    Main entry point for crawl4ai scraper.
    
    Args:
        limit: Optional limit on number of articles to return
        
    Returns:
        List of SourceArticle objects
    """
    from utils.supabase import get_active_crawl_sources
    
    try:
        from crawl4ai import AsyncWebCrawler
    except ImportError:
        logger.error("crawl4ai not installed - crawl4ai scraping unavailable")
        return []
    
    logger.info("🚀 Starting crawl4ai scraper")
    
    # Get active crawl sources from database
    crawl_sources = get_active_crawl_sources()
    
    if not crawl_sources:
        logger.warning("No active crawl sources found")
        return []
    
    all_articles = []
    
    async with AsyncWebCrawler() as crawler:
        for source in crawl_sources:
            logger.info(f"🕷️ Processing crawl source: {source.name}")
            
            try:
                articles = await extract_articles(crawler, source)
                all_articles.extend(articles)
                logger.info(f"✅ Extracted {len(articles)} articles from {source.name}")
            except Exception as e:
                logger.error(f"Error processing crawl source {source.name}: {e}")
                continue
    
    # Apply limit if specified
    if limit and len(all_articles) > limit:
        all_articles = all_articles[:limit]
        logger.info(f"✂️ Limited results to {limit} articles")
    
    logger.info(f"✅ Crawl4ai scraper completed: {len(all_articles)} articles")
    return all_articles


if __name__ == "__main__":
    # For testing the scraper directly
    import argparse
    import asyncio
    
    parser = argparse.ArgumentParser(description="Crawl4AI Web Scraper")
    parser.add_argument("--limit", type=int, help="Limit number of articles")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to database")
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    articles = asyncio.run(run(limit=args.limit))
    
    if args.dry_run:
        logger.info(f"🔎 Dry run: would write {len(articles)} articles to database")
    else:
        from utils.supabase import upsert_source_articles
        inserted = upsert_source_articles(articles)
        logger.info(f"💾 Inserted {len(inserted)} new articles to database")
