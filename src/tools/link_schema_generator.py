"""
Link schema generation tool for Scroopy agent
"""

import ast
import json
import logging
import os
from typing import Dict
from pathlib import Path
import asyncio

# Import rate limiting
from utils.rate_limiter import rate_limited, wait_for_rate_limit, get_rate_limiter_stats

logger = logging.getLogger(__name__)

@rate_limited
async def generate_link_schema(base_url: str) -> str:
    """
    Generate and validate CSS extraction schema for finding article links on a news homepage
    
    Args:
        base_url: The base URL of the news website
        
    Returns:
        JSON string with status and schema or error details
    """
    from utils.crawler_manager import get_shared_crawler
    
    logger.info(f"🔗 Generating link schema for: {base_url}")
    
    # Log rate limiter stats
    stats = get_rate_limiter_stats()
    logger.info(f"📊 Rate limiter: {stats['requests_in_last_minute']}/{stats['requests_per_minute_limit']} requests in last minute")
    
    try:
        # Fetch homepage content using shared crawler
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
        if not html_content or len(html_content) < 100:
            error_msg = f"No substantial content found on: {base_url}"
            logger.error(f"❌ {error_msg}")
            return json.dumps({
                "status": "error", 
                "error": error_msg
            })
        
        logger.info(f"   🔍 Analyzing {len(html_content)} characters of HTML")
        
        # Generate schema with LLM (rate limiting handled by decorator)
        max_retries = 3
        api_key = os.getenv('GOOGLE_API_KEY')
        
        for attempt in range(max_retries):
            print(f"   🤖 Analyzing HTML structure with LLM (attempt {attempt + 1}/{max_retries})...")
            
            try:
                # Additional manual rate limiting for safety
                if attempt > 0:
                    await wait_for_rate_limit()
                
                from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
                from crawl4ai import LLMConfig
                
                schema = JsonCssExtractionStrategy.generate_schema(
                    html=html_content,
                    llm_config=LLMConfig(
                        provider="gemini/gemini-2.0-flash",
                        api_token=api_key
                    ),
                    query="""
You are an expert in building structured web extraction schemas for Crawl4AI.

CRITICAL: You MUST return ONLY valid JSON. Do not wrap in markdown, do not add explanations, do not use Python dict syntax with single quotes.

Here are examples of the EXACT JSON format required:

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

Based on the HTML provided, generate a JSON schema that extracts ONLY individual article URLs.

CRITICAL REQUIREMENTS:
- Return ONLY valid JSON (double quotes, proper syntax)
- Extract ONLY individual article URLs - NOT category pages, topic sections, or navigation links
- Target links that go to SPECIFIC NEWS ARTICLES with headlines/stories
- AVOID links to category pages like "/politics/", "/sports/", "/business/"
- AVOID navigation links, menu items, or section headers
- Look for links that typically have article titles or headlines as link text
- Use exactly one field named "article_url" with type "attribute" and attribute "href"
- Choose a baseSelector that targets the main article links on the page
- Avoid positional selectors like nth-child
- Prefer class-based selectors

EXAMPLES OF WHAT TO TARGET:
✅ Links to: "/news/politics/trump-announces-new-policy-2025-06-15"
✅ Links to: "/articles/breaking-news-election-results"
✅ Links to: "/story/local-mayor-resigns-scandal"

EXAMPLES OF WHAT TO AVOID:
❌ Links to: "/politics/" (category page)
❌ Links to: "/sports/" (section page)
❌ Links to: "/about-us" (navigation)
❌ Links to: "/contact" (navigation)

Return ONLY the JSON object, nothing else.
"""
                )
                
                if not schema:
                    print(f"   ❌ LLM returned empty schema on attempt {attempt + 1}")
                    if attempt < max_retries - 1:
                        print(f"   🔄 Retrying schema generation...")
                        continue
                    else:
                        return json.dumps({
                            "status": "error",
                            "error": "LLM failed to generate schema after all retries"
                        })
                
                # Handle response format
                if isinstance(schema, list):
                    if len(schema) > 0:
                        response_text = str(schema[0]).strip()
                    else:
                        response_text = ""
                else:
                    response_text = str(schema).strip()
                
                print(f"   📝 LLM Response (length: {len(response_text)}):")
                print(f"   📝 First 200 chars: {response_text[:200]}...")
                
                # Parse and validate schema
                try:
                    # Try JSON parsing first
                    try:
                        schema_obj = json.loads(response_text)
                        print(f"   ✅ Parsed as valid JSON")
                    except json.JSONDecodeError:
                        # If JSON fails, try to convert Python dict syntax to JSON
                        print(f"   🔧 JSON parsing failed, trying Python dict conversion...")
                        
                        # Use ast.literal_eval to safely parse Python dict syntax
                        try:
                            schema_obj = ast.literal_eval(response_text)
                            print(f"   ✅ Successfully parsed Python dict with ast.literal_eval")
                        except (ValueError, SyntaxError) as ast_error:
                            print(f"   ❌ ast.literal_eval failed: {ast_error}")
                            print(f"   📝 Original text: {response_text}")
                            raise ast_error
                    
                    # Validate required fields
                    required_fields = ["name", "baseSelector", "fields"]
                    if not all(field in schema_obj for field in required_fields):
                        missing_fields = [f for f in required_fields if f not in schema_obj]
                        print(f"   ❌ Schema missing required fields: {missing_fields}")
                        
                        if attempt < max_retries - 1:
                            print(f"   🔄 Retrying with field requirements...")
                            continue
                        else:
                            return json.dumps({
                                "status": "error",
                                "error": f"Schema missing required fields: {missing_fields}"
                            })
                    
                    # Validate that we have exactly one field named "article_url"
                    fields = schema_obj.get("fields", [])
                    if len(fields) != 1:
                        print(f"   ❌ Schema should have exactly 1 field, got {len(fields)}")
                        
                        if attempt < max_retries - 1:
                            print(f"   🔄 Retrying with single field requirement...")
                            continue
                        else:
                            return json.dumps({
                                "status": "error",
                                "error": f"Schema should have exactly 1 field (article_url), got {len(fields)}"
                            })
                    
                    field = fields[0]
                    if field.get("name") != "article_url":
                        print(f"   ❌ Field should be named 'article_url', got '{field.get('name')}'")
                        
                        if attempt < max_retries - 1:
                            print(f"   🔄 Retrying with correct field name...")
                            continue
                        else:
                            return json.dumps({
                                "status": "error",
                                "error": f"Field should be named 'article_url', got '{field.get('name')}'"
                            })
                    
                    print(f"   ✅ Generated schema with {len(fields)} field")
                    print(f"   🎯 Confidence: high")
                    
                    return json.dumps({
                        "status": "success",
                        "schema": schema_obj,
                        "confidence": "high"
                    })
                    
                except Exception as e:
                    print(f"   ❌ Schema generation failed on attempt {attempt + 1}: {e}")
                    print(f"   📝 Raw schema response: {response_text}")
                    
                    if attempt < max_retries - 1:
                        print(f"   🔄 Retrying with JSON format requirements...")
                        continue
                    else:
                        return json.dumps({
                            "status": "error",
                            "error": f"Generated schema is invalid JSON: {str(e)}"
                        })
                        
            except Exception as e:
                print(f"   ❌ Schema generation failed on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    print(f"   🔄 Retrying schema generation...")
                    await asyncio.sleep(2)  # Wait before retry
                    continue
                else:
                    return json.dumps({
                        "status": "error",
                        "error": f"Schema generation failed after all retries: {str(e)}"
                    })
        
        # This should never be reached
        return json.dumps({
            "status": "error",
            "error": "Schema generation failed - unexpected end of retry loop"
        })
        
    except Exception as e:
        logger.error(f"❌ Link schema generation failed: {e}")
        return json.dumps({
            "status": "error",
            "error": f"Link schema generation failed: {str(e)}"
        }) 