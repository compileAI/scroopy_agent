"""
Web fetching tool for Scroopy agent
"""

import json
import logging
import tempfile
import os
from pathlib import Path
from typing import Dict

from utils.crawler_manager import get_shared_crawler

logger = logging.getLogger(__name__)

# Global temp directory for storing fetched content
TEMP_DIR = Path(tempfile.gettempdir()) / "scroopy_cache"
TEMP_DIR.mkdir(exist_ok=True)

async def fetch_webpage(url: str) -> str:
    """
    Fetch webpage content for analysis
    
    Args:
        url: The URL to fetch
        
    Returns:
        JSON string with status and content or error details
    """
    logger.info(f"🌐 TOOL: fetch_webpage - Getting content from {url}")
    print(f"🌐 TOOL: fetch_webpage - Getting content from {url}")
    
    try:
        print(f"   └─ Starting Crawl4AI async operation...")
        print(f"   🕷️ Crawl4AI fetching: {url}")
        
        # Use shared crawler
        crawler = await get_shared_crawler()
        result = await crawler.arun(url=url)
        
        if not result.success:
            error_msg = f"Failed to fetch {url}: Crawl4AI returned unsuccessful result"
            logger.error(f"❌ {error_msg}")
            print(f"   ❌ Error: {error_msg}")
            return json.dumps({
                "status": "error",
                "error": error_msg
            })
        
        content = result.html
        if not content:
            error_msg = f"No content returned from {url}"
            logger.error(f"❌ {error_msg}")
            print(f"   ❌ Error: {error_msg}")
            return json.dumps({
                "status": "error",
                "error": error_msg
            })
        
        cleaned_content = result.cleaned_html or result.markdown or ""
        
        content_length = len(content)
        cleaned_length = len(cleaned_content)
        
        print(f"   ✅ Success: {content_length} characters fetched")
        print(f"   🧹 Cleaned content: {cleaned_length} characters")
        
        return json.dumps({
            "status": "success",
            "url": url,
            "content": content,
            "metadata": {
                "content_length": content_length,
                "cleaned_content_length": cleaned_length,
                "final_url": url
            }
        })
            
    except Exception as e:
        error_msg = f"Exception while fetching {url}: {str(e)}"
        logger.error(error_msg)
        print(f"   ❌ Exception: {error_msg}")
        
        return json.dumps({
            "status": "error", 
            "url": url,
            "error": error_msg
        }) 