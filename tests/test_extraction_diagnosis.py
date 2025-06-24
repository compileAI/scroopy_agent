#!/usr/bin/env python3

import asyncio
import os
import json
from pathlib import Path
import sys

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

async def diagnose_schema_extraction():
    """Diagnose exactly what's happening with schema extraction"""
    print("🔍 SCHEMA EXTRACTION DIAGNOSIS")
    print("=" * 60)
    
    try:
        from tools.article_schema_generator import extract_article_with_schema
        from utils.crawler_manager import get_shared_crawler
        
        # Test URL
        test_url = "https://techcrunch.com/2025/06/20/anthropic-says-most-ai-models-not-just-claude-will-resort-to-blackmail/"
        
        # Sample schema from the test run
        test_schema = {
            "name": "TechCrunch Article",
            "baseSelector": "main.wp-block-group",
            "fields": [
                {
                    "name": "title",
                    "selector": "h1.article-hero__title",
                    "type": "text"
                },
                {
                    "name": "content",
                    "selector": "div.entry-content p",
                    "type": "nested_list",
                    "fields": [
                        {
                            "name": "text",
                            "type": "text"
                        }
                    ]
                },
                {
                    "name": "date_published",
                    "selector": "time",
                    "type": "attribute",
                    "attribute": "datetime"
                },
                {
                    "name": "author",
                    "selector": "div.wp-block-tc23-author-card-name a",
                    "type": "text"
                }
            ]
        }
        
        print(f"🎯 Testing URL: {test_url}")
        print(f"🧰 Using schema: {test_schema['name']}")
        print(f"📍 Base selector: {test_schema['baseSelector']}")
        
        # Extract with the schema
        result = await extract_article_with_schema(test_url, test_schema)
        
        print("\n📋 EXTRACTION RESULT:")
        print("=" * 40)
        
        if result:
            print(f"✅ Success: {result.get('success', False)}")
            
            if result.get('success'):
                print(f"📝 Title: '{result.get('title', 'MISSING')}'")
                print(f"👤 Author: '{result.get('author', 'MISSING')}'")
                print(f"📅 Date: '{result.get('date_published', 'MISSING')}'")
                
                content = result.get('content', [])
                if content:
                    content_text = ' '.join([
                        item.get('text', '') if isinstance(item, dict) else str(item)
                        for item in content
                    ])
                    print(f"📄 Content length: {len(content_text)} chars")
                    print(f"📄 Content preview: '{content_text[:200]}...'")
                else:
                    print("📄 Content: MISSING")
                
                # Run objective quality check
                from tools.article_schema_generator import calculate_objective_extraction_quality
                quality = calculate_objective_extraction_quality(result)
                print(f"\n🎯 Quality Score: {quality['score']}/100")
                print(f"🚨 Issues: {quality.get('issues', [])}")
            else:
                print("❌ Extraction failed")
                print(f"❌ Error: {result.get('error', 'Unknown error')}")
        else:
            print("❌ No result returned")
        
        # Also try to fetch raw HTML to see what selectors are available
        print("\n🔍 HTML ANALYSIS:")
        print("=" * 40)
        
        crawler = await get_shared_crawler()
        from tools.article_schema_generator import fetch_article_html
        
        html = await fetch_article_html(test_url, crawler)
        if html:
            print(f"📄 HTML length: {len(html):,} chars")
            
            # Check for common selectors
            selectors_to_check = [
                "main.wp-block-group",
                "h1.article-hero__title", 
                "div.entry-content p",
                "time",
                "h1",
                "article",
                "main",
                "[class*='title']",
                "[class*='content']"
            ]
            
            for selector in selectors_to_check:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                elements = soup.select(selector)
                print(f"🎯 '{selector}': {len(elements)} elements found")
                if elements and len(elements) <= 3:
                    for i, elem in enumerate(elements[:3]):
                        text = elem.get_text(strip=True)[:100]
                        print(f"   [{i+1}] '{text}...'")
        
    except Exception as e:
        print(f"❌ Diagnosis failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(diagnose_schema_extraction()) 