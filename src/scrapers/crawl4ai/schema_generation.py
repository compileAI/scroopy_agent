"""
Schema generation for crawl4ai - ported from compile.
Combines link schema and article schema generation functionality.
"""
import os
import logging
from dotenv import load_dotenv
from typing import List

import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


def generate_link_schema(page_html) -> dict:
    """
    Generate a schema for extracting article links from a homepage.
    
    Args:
        page_html: Crawl4AI result object with HTML content
        
    Returns:
        Dictionary containing the extraction schema
    """
    try:
        from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
        from crawl4ai import LLMConfig
    except ImportError:
        logger.error("crawl4ai not installed - schema generation unavailable")
        return None
    
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.error("GEMINI_API_KEY not configured")
        return None
    
    try:
        # Generate a schema specifically for blog/article links  
        schema = JsonCssExtractionStrategy.generate_schema(  
            html=page_html.html,  
            llm_config=LLMConfig(  
                provider="gemini/gemini-2.0-flash",
                api_token=api_key
            ),
            query="""
            You are an expert in building structured web extraction schemas for Crawl4AI.

            Here are examples of good schemas:

            Example 1: Meta Schema (https://ai.meta.com/blog)
            {
                "name": "Meta Blog Posts",
                "baseSelector": "a._amcw",
                "fields": [
                    {
                    "name": "article_url",
                    "type": "attribute",
                    "attribute": "href"
                    }
                ]
            }

            Example 2: Google Schema (https://blog.google/technology/ai/)
            {
                "name": "Google Blog Posts",
                "baseSelector": "a.feed-article__overlay",
                "fields": [
                    {
                    "name": "article_url",
                    "type": "attribute",
                    "attribute": "href"
                    }
                ]
            }

            Example 3: Anthropic Schema (https://www.anthropic.com/news)
            {
                "name": "Anthropic Blog Posts",
                "baseSelector": "a.PostCard_post-card__z_Sqq",
                "fields": [
                    {
                    "name": "article_url",
                    "type": "attribute",
                    "attribute": "href"
                    }
                ]
            }

            ---

            Now, based on the following homepage HTML, generate a Crawl4AI-compatible JSON schema
            that extracts individual blog post article URLs.

            Important additional rules:
            - Define a baseSelector using a **CSS class name** that reflects blog post containers.
            - **NEVER use positional selectors** like `nth-child`, `nth-of-type`, or highly specific path selectors unless absolutely necessary.
            - Prefer baseSelectors with class names containing "blog", "post", "card", or "article".
            - Inside each container, extract a single field "article_url".
            - Use attribute "href" for article_url.
            - Output only pure JSON in the same format as examples.
            - Prefer using ">" between selectors where direct parent-child relationships exist.
            - Avoid using " " (descendant combinator) unless elements are nested deeply and variably.
            - Return a single JSON object representing the schema, not a list.
            - Do not return an array [...]. Only return a JSON object {...} with fields: name, baseSelector, and fields.
            - If there is more than one format for links, choose the one that shows up earlier and at the top of the page
            - If there are multiple formats or sections for article links, prioritize the primary/main article section that appears first and most prominently on the page.
            - Ignore secondary sections such as footers, sidebars, or "older posts" lists unless no main articles are present.

            Return only pure JSON in the same structure as the examples.
            """
        )
        
        logger.info("✅ Generated link schema successfully")
        return schema
        
    except Exception as e:
        logger.error(f"Error generating link schema: {e}")
        return None


async def generate_article_schema(urls: List[str], crawler) -> dict:
    """
    Generate a schema for extracting structured article content from a list of URLs.
    
    Args:
        urls: List of article URLs to analyze
        crawler: AsyncWebCrawler instance for making HTTP requests
        
    Returns:
        Dictionary containing the extraction schema
    """
    try:
        from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
        from crawl4ai import LLMConfig
    except ImportError:
        logger.error("crawl4ai not installed - schema generation unavailable")
        return None
    
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        logger.error("GEMINI_API_KEY not configured")
        return None
    
    # Fetch HTML content from the provided URLs
    pages_html = await fetch_article_html(urls, crawler)

    if not pages_html:
        logger.error("No pages successfully fetched for schema generation")
        return None
        
    combined_html = "\n\n---\n\n".join(pages_html)

    try:
        # Generate a schema specifically for blog/article content
        schema = JsonCssExtractionStrategy.generate_schema(  
            html=combined_html,  
            llm_config=LLMConfig(  
                provider="gemini/gemini-2.0-flash",
                api_token=api_key
            ),
            verbose=True,
            query="""    
        You are an expert in building Crawl4AI-compatible web extraction schemas.    
          
        You are given examples of individual article pages from the same website.    
          
        Your task is to generate a **single JSON object** (not a list) representing the schema to extract structured information.    
          
        Schema Requirements:    
        - There is exactly **one article per page**.    
        - Extract **only** the following 4 fields:    
        - "title" (the article headline)    
        - "content" (the full readable body text, as a nested list of paragraphs)    
        - "date_published" (the publication date)    
        - "author" (the author, if available)    
        - **No other fields** besides these 4 are allowed.    
          
        Field Extraction Rules:    
        - "title": select the main heading text, usually from an <h1> tag.    
        - "content":    
            - CRITICAL: The "content" field MUST capture ALL text content from the article body.    
            - You MUST use `"type": "nested_list"` for the content field.  
            - Your selector should target all paragraph elements in the article body.  
            - Define a sub-field called "text" with `"selector": "."` and `"type": "text"`.  
            - Your selector MUST include ALL possible text containers:  
                * Main content containers: article, .article-content, .post-content, .entry-content  
                * Text elements: p, h1, h2, h3, h4, h5, h6  
                * Lists: ul li, ol li  
                * Quotes: blockquote, q  
                * Code blocks: pre, code  
                * Other text: div.text, span.text  
            - Example selector: "article p, article h2, article h3, article ul li, article ol li, article blockquote"  
            - If the article uses a specific container class, include it in your selector  
            - The selector should be broad enough to capture everything but specific enough to avoid navigation or sidebar content  
        - "date_published": extract from a <time> tag; use "attribute": "datetime" if available.    
        - "author": extract the visible author text if present.    
          
        General Extraction Rules:    
        - Define a **single baseSelector** targeting the article container (e.g., <article>, <section>, <div class="article-content">).    
        - Prefer class-based or semantic selectors.    
        - Avoid using "nth-child", "nth-of-type", or deeply positional selectors unless absolutely necessary.    
        - Return a **single pure JSON object**, not a list.    
          
        Example desired output:    
          
        {  
                    'name': 'Meta AI Blog Posts',  
                    'baseSelector': 'body',  
                    'fields': [  
                        {  
                            "name": "title",  
                            "selector": "span._amgd",  
                            "type": "text"
                        },  
                        {  
                            "name": "content",  
                            "selector": "div._a5ci._a5cs._a92o._a5c-._a5w7 p",  
                            "type": "nested_list", 
                            "all": True,
                            "fields": [
                                {
                                    "name": "text",
                                    "type": "text"
                                }
                            ]
                        },  
                        {  
                            "name": "date_published",  
                            "selector": "span._amum",  
                            "type": "text"
                        }  
                    ]  
                }    
          
        IMPORTANT NOTES:    
        1. The "nested_list" type for the content field is ESSENTIAL to collect all paragraphs as separate items.  
        2. Make sure your content selector is comprehensive enough to capture ALL text elements.    
        3. Ensure proper JSON syntax with commas between field objects.    
        4. Test your content selector to verify it captures the ENTIRE article, not just the first paragraph.  
        5. If you're unsure about a selector, make it broader rather than narrower to ensure complete content capture.  
          
        If you generate a schema that contains fields not listed above, it will be rejected.    
        """
        )
        
        logger.info("✅ Generated article schema successfully")
        return schema
        
    except Exception as e:
        logger.error(f"Error generating article schema: {e}")
        return None


async def fetch_article_html(urls: List[str], crawler) -> List[str]:
    """
    Fetch HTML content from a list of article URLs.
    
    Args:
        urls: List of article URLs to fetch
        crawler: AsyncWebCrawler instance for making HTTP requests
        
    Returns:
        List of HTML content strings from successfully fetched pages
    """
    try:
        from crawl4ai import CrawlerRunConfig
        from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
    except ImportError:
        logger.error("crawl4ai not installed - HTML fetching unavailable")
        return []
    
    html_pages = []
    
    # Configure crawler for article pages
    config = CrawlerRunConfig(
        scraping_strategy=LXMLWebScrapingStrategy(),  # Use LXML for efficient HTML parsing
        verbose=True,  # Enable detailed logging
        delay_before_return_html=2,  # Wait 2 seconds to ensure dynamic content loads
        js_code=["window.scrollTo(0, document.body.scrollHeight);"]  # Scroll to bottom to trigger lazy loading
    )
    
    # Fetch HTML from each URL
    for url in urls:
        try:
            result = await crawler.arun(url, config=config)
            if result.success and result.html:
                html_pages.append(result.html)
                logger.debug(f"✅ Fetched HTML from {url}")
            else:
                logger.warning(f"❌ Failed to fetch {url}")
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")

    logger.info(f"Fetched HTML from {len(html_pages)} out of {len(urls)} URLs")
    return html_pages
