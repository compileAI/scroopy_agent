"""
LLM-based article extraction fallback for crawl4ai - ported from compile.
Provides robust article extraction using LLM when schema-based extraction fails.
"""
import json
import os
import re
import logging
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv

import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from models.source_article import SourceArticle
from models.news_sources import NewsSource
from utils.date_utils import safe_parse_date
from utils.gemini_api_manager import get_current_api_key

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


async def extract_article_with_llm(crawler, url: str, source: NewsSource) -> Optional[SourceArticle]:
    """
    Extract article content using Crawl4AI's LLM extraction as a fallback.
    
    This function provides robust article extraction when schema-based methods fail.
    Uses Gemini LLM to intelligently extract article content from web pages.
    
    Args:
        crawler: AsyncWebCrawler instance
        url: URL of the article to extract
        source: NewsSource object containing source metadata
        
    Returns:
        SourceArticle: Extracted article object, or None if extraction fails
    """
    try:
        from crawl4ai.extraction_strategy import LLMExtractionStrategy
        from crawl4ai import LLMConfig, CrawlerRunConfig
    except ImportError:
        logger.error("crawl4ai not installed - LLM extraction unavailable")
        return None
    
    # Get current API key from the manager (supports key rotation)
    try:
        api_key = get_current_api_key()
    except Exception as e:
        logger.error(f"Failed to get Gemini API key: {e}")
        return None
    
    try:
        logger.info(f"🤖 Starting LLM extraction for: {url}")
        
        # LLM extraction strategy following the documentation
        llm_strategy = LLMExtractionStrategy(
            llm_config=LLMConfig(
                provider="gemini/gemini-2.5-flash-lite",
                api_token=api_key
            ),
            schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The exact main article title/headline as it appears"},
                    "content": {"type": "string", "description": "Clean article text only - no markdown, no formatting, just plain text"},
                    "date_published": {"type": "string", "description": "Publication date in any format found"},
                    "author": {"type": "string", "description": "Author name exactly as shown"}
                },
                "required": ["title", "content"]
            },
            extraction_type="schema",
            instruction="""Extract the main article content from this webpage.

CRITICAL REQUIREMENTS:
1. title: Find the PRIMARY article headline - usually the largest, most prominent heading
   - Look for <h1> tags or prominent headings
   - Should be a complete, meaningful article title
   - NOT generic titles like "Home" or site names

2. content: Extract the COMPLETE main article body as PLAIN TEXT:
   - Extract ALL paragraphs, subheadings, and text from the article
   - Include the full article from beginning to end
   - NO markdown formatting (no **, __, [], etc.)
   - NO HTML tags
   - Convert to clean plain text with proper paragraph breaks
   - Should be substantial content (200+ characters minimum)

3. date_published: Find the article's publication date (any format)
4. author: Find the article author's name

Focus on extracting the main article content, ignoring navigation, ads, sidebars, and other non-article elements.""",
            chunk_token_threshold=8000,  # Handle large articles
            overlap_rate=0.1,
            apply_chunking=True,
            input_format="markdown",  # Use markdown for cleaner text processing
            extra_args={"temperature": 0.1, "max_tokens": 2000}
        )
        
        # Standard crawler config with LLM strategy
        config = CrawlerRunConfig(
            extraction_strategy=llm_strategy,
            verbose=True,
            delay_before_return_html=3
        )
        
        # Execute LLM extraction
        result = await crawler.arun(url, config=config)
        
        if not result.success or not result.extracted_content:
            logger.error("LLM extraction failed - no content returned")
            return None
            
        # Parse the LLM response
        try:
            extracted_data = json.loads(result.extracted_content)
            
            # Handle list response (take first item)
            if isinstance(extracted_data, list) and len(extracted_data) > 0:
                data = extracted_data[0]
            elif isinstance(extracted_data, dict):
                data = extracted_data
            else:
                logger.error(f"LLM extraction returned unexpected format: {type(extracted_data)}")
                return None
                
        except json.JSONDecodeError as e:
            logger.error(f"LLM extraction JSON parsing failed: {e}")
            return None
        
        # Validate and extract fields
        if not isinstance(data, dict):
            logger.error(f"LLM extraction data is not a dict: {type(data)}")
            return None
        
        title = str(data.get('title', '')).strip()
        content = str(data.get('content', '')).strip()
        
        # Validate required fields
        if not title:
            logger.warning("LLM extraction: no title found")
            title = "LLM_EXTRACTION_NO_TITLE"
        
        if not content or len(content) < 50:
            logger.warning(f"LLM extraction: insufficient content ({len(content)} chars)")
            return None
        
        # Clean up any remaining markdown formatting
        content = _clean_markdown_formatting(content)
        
        # Parse publication date safely
        published_date = safe_parse_date(data.get('date_published', ''))
        if published_date is None:
            published_date = datetime.now(timezone.utc)
        
        # Extract author
        author = str(data.get('author', '')).strip() if data.get('author') else ''
        
        logger.info(f"✅ LLM extraction successful:")
        logger.info(f"   📝 Title: {title}")
        logger.info(f"   📝 Content length: {len(content)} characters")
        logger.info(f"   📝 Author: {author}")
        logger.info(f"   📝 Published: {published_date}")
        
        # Show token usage for debugging
        try:
            llm_strategy.show_usage()
        except:
            pass  # Usage info might not be available
        
        # Create and return SourceArticle object
        return SourceArticle(
            published=published_date,
            title=title,
            content=content,
            author=author,
            source_id=source.source_id,
            url=url
        )
            
    except ImportError:
        logger.error("LLM extraction dependencies not available")
        return None
    except Exception as e:
        logger.error(f"LLM extraction exception: {e}")
        return None


def _clean_markdown_formatting(content: str) -> str:
    """
    Clean up any remaining markdown formatting from the content.
    
    Args:
        content: Raw content that may contain markdown
        
    Returns:
        Clean plain text content
    """
    # Remove bold formatting
    content = re.sub(r'\*\*([^*]+)\*\*', r'\1', content)
    content = re.sub(r'__([^_]+)__', r'\1', content)
    
    # Remove italic formatting
    content = re.sub(r'\*([^*]+)\*', r'\1', content)
    content = re.sub(r'_([^_]+)_', r'\1', content)
    
    # Remove links (keep link text)
    content = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', content)
    
    # Clean up excessive whitespace
    content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
    content = re.sub(r'[ \t]+', ' ', content)
    
    return content.strip()


