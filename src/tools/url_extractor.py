"""
URL Extractor Tool

Extracts article URLs from webpages using CSS schemas
"""

import json
import logging
import asyncio
from typing import List, Dict, Any
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

async def extract_urls_with_schema(base_url: str, schema_json: str, max_urls: int = 10) -> str:
    """
    Extract article URLs from a webpage using a CSS extraction schema
    
    Args:
        base_url: The base URL of the news website homepage
        schema_json: JSON string containing the CSS extraction schema
        max_urls: Maximum number of URLs to extract (default 10)
        
    Returns:
        JSON string with extracted URLs or error details
    """
    from utils.crawler_manager import get_shared_crawler
    
    logger.info(f"🔗 Extracting URLs from: {base_url}")
    logger.info(f"   🎯 Max URLs: {max_urls}")
    
    try:
        # Parse the schema
        try:
            if isinstance(schema_json, str):
                schema = json.loads(schema_json)
            else:
                schema = schema_json
                
            logger.info(f"   📋 Using schema: {schema.get('name', 'Unknown')}")
            logger.info(f"   🎯 Base selector: {schema.get('baseSelector', 'Unknown')}")
        except (json.JSONDecodeError, TypeError) as e:
            error_msg = f"Invalid schema JSON: {e}"
            logger.error(f"❌ {error_msg}")
            return json.dumps({
                "status": "error",
                "error": error_msg
            })
        
        # Fetch webpage content using shared crawler
        crawler = await get_shared_crawler()
        result = await crawler.arun(url=base_url)
        
        if not result.success:
            error_msg = f"Failed to fetch homepage: {base_url}"
            logger.error(f"❌ {error_msg}")
            return json.dumps({
                "status": "error", 
                "error": error_msg
            })
        
        html_content = result.html
        logger.info(f"   🔍 Analyzing {len(html_content)} characters of HTML")
        
        # Extract URLs using the schema with Crawl4AI
        try:
            from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
            
            # Create extraction strategy with the provided schema
            extraction_strategy = JsonCssExtractionStrategy([schema])
            
            # Extract using the strategy
            extraction_result = await crawler.arun(
                url=base_url,
                extraction_strategy=extraction_strategy
            )
            
            if not extraction_result.success:
                error_msg = f"Extraction failed for {base_url}"
                logger.error(f"❌ {error_msg}")
                return json.dumps({
                    "status": "error",
                    "error": error_msg
                })
            
            # Parse the extracted data
            extracted_data = extraction_result.extracted_content
            
            logger.info(f"   📊 Raw extraction result type: {type(extracted_data)}")
            
            # Handle different response formats
            urls = []
            if isinstance(extracted_data, list) and len(extracted_data) > 0:
                # Get the first extraction result
                data = extracted_data[0]
                if isinstance(data, dict) and schema['name'] in data:
                    items = data[schema['name']]
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict) and 'article_url' in item:
                                url = item['article_url']
                                if url:
                                    # Convert relative URLs to absolute
                                    absolute_url = urljoin(base_url, url)
                                    urls.append(absolute_url)
                                    logger.info(f"         [URL {len(urls)}] {absolute_url}")
                                    
                                    if len(urls) >= max_urls:
                                        break
            
            # Alternative extraction using BeautifulSoup as fallback
            if not urls:
                logger.info("   🔄 Trying BeautifulSoup fallback extraction...")
                from bs4 import BeautifulSoup
                
                soup = BeautifulSoup(html_content, 'html.parser')
                base_selector = schema.get('baseSelector', '')
                
                # Try to parse CSS selector 
                try:
                    elements = soup.select(base_selector)
                    logger.info(f"         🔍 Found {len(elements)} elements matching: {base_selector}")
                    
                    for i, element in enumerate(elements[:max_urls], 1):
                        # Extract href attribute
                        href = element.get('href')
                        if href:
                            absolute_url = urljoin(base_url, href)
                            
                            # Basic validation - should look like an article URL
                            parsed = urlparse(absolute_url)
                            if parsed.scheme in ['http', 'https'] and parsed.netloc:
                                urls.append(absolute_url)
                                logger.info(f"         [URL {len(urls)}] {absolute_url}")
                        
                        if len(urls) >= max_urls:
                            break
                            
                except Exception as selector_error:
                    logger.warning(f"   ⚠️ CSS selector parsing failed: {selector_error}")
            
            # Remove duplicates while preserving order
            unique_urls = []
            seen = set()
            for url in urls:
                if url not in seen:
                    unique_urls.append(url)
                    seen.add(url)
            
            logger.info(f"   📈 Extracted {len(urls)} URLs, {len(unique_urls)} unique")
            
            if not unique_urls:
                return json.dumps({
                    "status": "warning",
                    "message": "No URLs extracted - schema may need adjustment",
                    "urls": [],
                    "count": 0
                })
            
            # Limit to max_urls
            final_urls = unique_urls[:max_urls]
            
            logger.info(f"   🏁 Final result: {len(final_urls)} URLs")
            for i, url in enumerate(final_urls, 1):
                logger.info(f"      {i}. {url}")
            
            return json.dumps({
                "status": "success",
                "urls": final_urls,
                "count": len(final_urls),
                "base_url": base_url,
                "schema_name": schema.get('name', 'Unknown')
            })
            
        except Exception as extraction_error:
            logger.error(f"❌ URL extraction failed: {extraction_error}")
            return json.dumps({
                "status": "error",
                "error": f"URL extraction failed: {str(extraction_error)}"
            })
        
    except Exception as e:
        logger.error(f"❌ URL extraction failed: {e}")
        return json.dumps({
            "status": "error",
            "error": f"URL extraction failed: {str(e)}"
        }) 