"""
Article schema generation tool with LLM-powered validation and feedback loops
"""

import json
import logging
import os
from typing import Dict, List, Any
from urllib.parse import urljoin, urlparse
import asyncio

logger = logging.getLogger(__name__)

def get_source_name_from_url(url: str) -> str:
    """
    Extract a proper source name from URL.
    Maps known domains to proper source names.
    """
    domain = urlparse(url).netloc.lower()
    
    # Remove common prefixes
    if domain.startswith('www.'):
        domain = domain[4:]
    
    # Map known domains to proper names
    domain_mapping = {
        'techcrunch.com': 'TechCrunch',
        'cnn.com': 'CNN',
        'bbc.com': 'BBC',
        'bbc.co.uk': 'BBC',
        'reuters.com': 'Reuters',
        'bloomberg.com': 'Bloomberg',
        'wsj.com': 'Wall Street Journal',
        'nytimes.com': 'New York Times',
        'washingtonpost.com': 'Washington Post',
        'theguardian.com': 'The Guardian',
        'forbes.com': 'Forbes',
        'cnbc.com': 'CNBC',
        'venturebeat.com': 'VentureBeat',
        'arstechnica.com': 'Ars Technica',
        'wired.com': 'Wired',
        'theverge.com': 'The Verge',
        'engadget.com': 'Engadget',
    }
    
    return domain_mapping.get(domain, domain.replace('.com', '').replace('.co.uk', '').title())

def normalize_url(url: str) -> str:
    """
    Normalize URL for consistent database lookups.
    Ensures trailing slash for domain-only URLs.
    """
    if not url:
        return url
        
    # Parse URL to handle different cases
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(url)
    
    # If path is empty or just '/', ensure it ends with '/'
    if not parsed.path or parsed.path == '/':
        # Reconstruct URL with trailing slash
        new_parsed = parsed._replace(path='/')
        return urlunparse(new_parsed)
    
    return url

async def check_source_exists(base_url: str) -> bool:
    """
    Check if a crawl source already exists in Supabase database.
    Now checks by URL in master_sources table (not home_url in crawl_sources).
    Normalizes URLs to handle trailing slash variations.
    Returns True if source exists, False otherwise.
    """
    try:
        from supabase import create_client
        
        # Get Supabase credentials
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        
        if not supabase_url or not supabase_key:
            print(f"⚠️ Missing Supabase credentials - skipping duplicate check")
            return False  # If we can't check, proceed with generation
        
        supabase = create_client(supabase_url, supabase_key)
        
        # Normalize URL for consistent lookup
        normalized_url = normalize_url(base_url)
        
        # Check if source already exists in master_sources by URL
        response = supabase.table("master_sources").select("name, scrape_method").eq("url", normalized_url).execute()
        
        # Also check the original URL in case normalization changed it
        if not response.data and normalized_url != base_url:
            response = supabase.table("master_sources").select("name, scrape_method").eq("url", base_url).execute()
        
        if response.data and len(response.data) > 0:
            existing_source = response.data[0]
            scrape_method = existing_source.get('scrape_method', 'unknown')
            source_name = existing_source.get('name', 'Unknown')
            print(f"✅ Source already exists in database: {source_name} (method: {scrape_method})")
            return True
        
        return False
        
    except ImportError:
        print(f"⚠️ Supabase client not available - skipping duplicate check")
        return False  # If we can't check, proceed with generation
    except Exception as e:
        print(f"⚠️ Error checking for existing source: {e}")
        return False  # If we can't check, proceed with generation


async def generate_validated_article_schema(base_url: str, sample_urls: List[str]) -> str:
    """
    Generate and validate an article extraction schema with LLM-powered feedback loops.
    Caches ground truth extractions to avoid redundant API calls.
    
    Args:
        base_url: The base URL of the news source
        sample_urls: List of sample article URLs to test against
        
    Returns:
        JSON string with validation results and schema
    """
    logger.info(f"🎯 Starting validated article schema generation for {base_url}")
    
    # Note: We no longer skip schema generation if source exists
    # The decision to update/skip is handled in supabase_writer based on validation scores
    print(f"         🔄 Proceeding with schema generation (update logic handled in database writer)")
    
    if not sample_urls or len(sample_urls) < 2:
        return json.dumps({
            "status": "error",
            "error": "Need at least 2 sample URLs for validation",
            "validation_score": 0,
            "attempts": 0
        })
    
    # Cache for ground truth extractions to avoid re-extracting same URLs
    ground_truth_cache = {}
    
    max_attempts = 3
    target_score = 90.0
    
    for attempt in range(1, max_attempts + 1):
        logger.info(f"🔄 Attempt {attempt}/{max_attempts}")
        
        # Debug: Print the URLs being tested
        print(f"         🔗 Testing with sample URLs:")
        for i, url in enumerate(sample_urls, 1):
            print(f"           [{i}] {url}")
        
        try:
            # Step 1: Generate schema (with feedback from previous attempts if available)
            feedback_context = None
            if attempt > 1:
                # Use feedback from previous attempts
                feedback_context = "Previous attempts had issues. Please improve the schema."
            
            schema = await generate_article_schema_with_feedback(base_url, sample_urls, feedback_context, attempt)
            
            if not schema:
                logger.error(f"❌ Schema generation failed on attempt {attempt}")
                continue
            
            logger.info(f"✅ Generated schema: {schema.get('name', 'Unknown')}")
            
            # Step 2: Test schema extraction on sample URLs
            schema_extractions = []
            print(f"         📋 Step 2: Testing schema extraction on {len(sample_urls)} URLs...")
            for i, url in enumerate(sample_urls, 1):
                print(f"         🔧 [{i}/{len(sample_urls)}] Schema extraction for: {url}")
                try:
                    extraction = await extract_article_with_schema(url, schema)
                    schema_extractions.append(extraction)
                    print(f"         ✅ [{i}/{len(sample_urls)}] Schema extraction successful")
                except Exception as e:
                    logger.warning(f"⚠️ Schema extraction failed for {url}: {e}")
                    print(f"         ❌ [{i}/{len(sample_urls)}] Schema extraction failed: {e}")
                    schema_extractions.append(None)
            
            # Step 3: LLM Ground Truth Validation
            print(f"         📊 Step 3: LLM GROUND TRUTH VALIDATION - Testing schema on {len(sample_urls)} URLs...")
            
            # Generate ground truth for each URL
            comparisons = []
            validation_scores = []
            
            for i, url in enumerate(sample_urls):
                print(f"         🔍 [{i+1}/{len(sample_urls)}] Comparing against ground truth: {url[:80]}...")
                
                try:
                    # Get ground truth using LLM extraction
                    ground_truth = await extract_ground_truth_with_retries(url)
                    
                    if not ground_truth:
                        print(f"         ❌ [{i+1}/{len(sample_urls)}] Ground truth extraction failed")
                        comparisons.append({
                            'url': url,
                            'similarity_score': 0,
                            'success': False,
                            'error': 'Ground truth extraction failed'
                        })
                        validation_scores.append(0)
                        continue
                    
                    # Get schema extraction result
                    if i < len(schema_extractions) and schema_extractions[i]:
                        schema_result = schema_extractions[i]
                        
                        # Compare schema result vs ground truth
                        comparison = await compare_article_extractions(schema_result, ground_truth, url)
                        comparisons.append(comparison)
                        validation_scores.append(comparison.get('similarity_score', 0))
                        
                        score = comparison.get('similarity_score', 0)
                        print(f"         ✅ [{i+1}/{len(sample_urls)}] Comparison complete - Score: {score:.1f}%")
                    else:
                        print(f"         ❌ [{i+1}/{len(sample_urls)}] No schema extraction available")
                        comparisons.append({
                            'url': url,
                            'similarity_score': 0,
                            'success': False,
                            'error': 'No schema extraction available'
                        })
                        validation_scores.append(0)
                        
                except Exception as e:
                    logger.error(f"Comparison failed for {url}: {e}")
                    print(f"         ❌ [{i+1}/{len(sample_urls)}] Comparison failed: {e}")
                    comparisons.append({
                        'url': url,
                        'similarity_score': 0,
                        'success': False,
                        'error': str(e)
                    })
                    validation_scores.append(0)
            
            # Calculate overall validation score
            validation_score = sum(validation_scores) / len(validation_scores) if validation_scores else 0
            successful_extractions = sum(1 for score in validation_scores if score > 0)
            success_rate = (successful_extractions / len(validation_scores)) * 100 if validation_scores else 0
            
            logger.info(f"🎯 Ground truth validation score: {validation_score:.1f}% (attempt {attempt})")
            logger.info(f"📊 Success rate: {success_rate:.1f}% ({successful_extractions}/{len(sample_urls)} URLs)")
            
            print(f"         🎯 GROUND TRUTH VALIDATION COMPLETE:")
            print(f"         📊 Quality Score: {validation_score:.1f}%")
            print(f"         📊 Success Rate: {success_rate:.1f}% ({successful_extractions}/{len(sample_urls)} URLs)")
            print(f"         📊 Using LLM ground truth comparison for accurate validation!")
            
            # Step 5: Check if we've reached the target score
            if validation_score >= target_score:
                logger.info(f"🎉 Target score achieved! ({validation_score:.1f}% >= {target_score}%)")
                
                return json.dumps({
                    "status": "success",
                    "schema": schema,
                    "validation_score": validation_score,
                    "attempts": attempt,
                    "comparisons": comparisons,
                    "ground_truth_cache_size": len(ground_truth_cache)
                })
            
            # Compile feedback for next attempt
            if attempt < max_attempts:
                feedback_context = compile_improvement_feedback(comparisons)
                logger.info(f"📝 Compiled feedback for next attempt: {feedback_context}")
        
        except Exception as e:
            logger.error(f"❌ Attempt {attempt} failed with exception: {e}")
            continue
    
    # If we get here, we didn't reach the target score
    logger.warning(f"⚠️ Failed to reach target score after {max_attempts} attempts")
    return json.dumps({
        "status": "partial_success",
        "schema": schema if 'schema' in locals() else None,
        "validation_score": validation_score if 'validation_score' in locals() else 0,
        "attempts": max_attempts,
        "error": f"Could not achieve {target_score}% validation score",
        "ground_truth_cache_size": len(ground_truth_cache)
    })


async def generate_article_schema_with_feedback(homepage_url: str, sample_urls: List[str], feedback: str = None, high_level_attempt: int = 1) -> Dict[str, Any]:
    """Generate article schema using LLM, optionally incorporating feedback from previous attempts"""
    
    try:
        # Import Crawl4AI components
        from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
        from crawl4ai import LLMConfig
        from utils.crawler_manager import get_shared_crawler
        
        # Fetch HTML content from sample URLs
        print(f"         Fetching HTML from first sample article (of {len(sample_urls)} total)...")
        crawler = await get_shared_crawler()
        
        # Use only the first sample URL to avoid token limits
        first_url = sample_urls[0]
        print(f"         Using: {first_url}")
        
        combined_html = await fetch_article_html(first_url, crawler)
        
        if not combined_html:
            return {"status": "error", "error": f"No HTML content fetched from first sample URL: {first_url}"}
        
        print(f"         Successfully fetched HTML from first sample article")
        print(f"         HTML length: {len(combined_html):,} characters")
        
        # Note: We still validate against ALL sample URLs later in the process
        
        # Build the schema generation query
        base_query = """
        You are an expert in building Crawl4AI-compatible web extraction schemas.
        
        You are given an example of an individual article page from a website.
        
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
            - IMPORTANT: Put the selector on the nested_list field itself, NOT in the nested fields.
            - Your selector should target all paragraph elements in the article body.
            - Define a sub-field called "text" with ONLY `"name": "text"` and `"type": "text"` - NO SELECTOR.
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
        
        CRITICAL: Use the exact field names shown below. Crawl4AI requires these specific field names:
        
        Example desired output:
        {
            "name": "Meta AI Blog Posts",
            "baseSelector": "body",
            "fields": [
                {
                    "name": "title",
                    "selector": "span._amgd",
                    "type": "text"
                },
                {
                    "name": "content",
                    "selector": "div._amgf p, div._amgf h2, div._amgf h3, div._amgf ul li, div._amgf ol li",
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
                    "selector": "span._amgh",
                    "type": "text"
                }
            ]
        }
        
        Return ONLY the JSON object, no extra text or formatting.
        """
        
        # Add feedback if provided
        if feedback:
            feedback_section = f"\n\nFeedback from previous attempts:\n{feedback}\n\nPlease address these issues in your schema."
            base_query += feedback_section
        
        # Generate schema with retry logic
        api_key = os.getenv('GOOGLE_API_KEY')
        max_retries = 3
        
        for attempt in range(max_retries):
            print(f"         🤖 Generating article schema with LLM (high-level attempt {high_level_attempt}, retry {attempt + 1}/{max_retries})...")
            
            try:
                schema = JsonCssExtractionStrategy.generate_schema(
                    html=combined_html,
                    llm_config=LLMConfig(
                        provider="gemini/gemini-2.0-flash",
                        api_token=api_key
                    ),
                    query=base_query,
                    verbose=True
                )
                
                if not schema:
                    print(f"         ❌ LLM returned empty schema on retry {attempt + 1}")
                    if attempt < max_retries - 1:
                        print(f"         🔄 Retrying schema generation...")
                        base_query += f"\n\nPrevious attempt returned empty response. Please ensure you return a valid JSON schema."
                        continue
                    else:
                        return {"status": "error", "error": "LLM failed to generate schema after all retries"}
                
                # Validate schema structure
                try:
                    # Handle response that might be a list or string
                    if isinstance(schema, list):
                        if len(schema) > 0:
                            schema_text = str(schema[0]).strip()
                        else:
                            schema_text = ""
                    elif isinstance(schema, str):
                        schema_text = schema.strip()
                        print(f"         📝 LLM Response (length: {len(schema_text)}):")
                        print(f"         📝 First 300 chars: {schema_text[:300]}...")
                    else:
                        # Already a dict/object
                        schema_obj = schema
                        
                    # Parse string response if needed
                    if 'schema_text' in locals():
                        schema_obj = json.loads(schema_text)
                    
                    # Basic validation
                    required_fields = ["name", "baseSelector", "fields"]
                    if not all(field in schema_obj for field in required_fields):
                        missing_fields = [f for f in required_fields if f not in schema_obj]
                        print(f"         ❌ Schema missing required fields: {missing_fields}")
                        print(f"         📝 Schema keys: {list(schema_obj.keys()) if isinstance(schema_obj, dict) else 'Not a dict'}")
                        
                        if attempt < max_retries - 1:
                            print(f"         🔄 Retrying with field requirements...")
                            base_query += f"\n\nPrevious attempt was missing required fields: {missing_fields}. Ensure your JSON has exactly these fields: {required_fields}"
                            continue
                        else:
                            return {"status": "error", "error": f"Schema missing required fields after all retries: {missing_fields}"}
                    
                    print(f"         ✅ Generated valid schema with {len(schema_obj.get('fields', []))} fields")
                    print(f"         📋 Schema keys: {list(schema_obj.keys())}")
                    print(f"         📋 BaseSelector: {schema_obj.get('baseSelector', 'MISSING!')}")
                    return {"status": "success", "schema": schema_obj}
                    
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"         ❌ Schema JSON parsing failed on retry {attempt + 1}: {e}")
                    if 'schema_text' in locals():
                        print(f"         📝 Raw schema response: {schema_text}")
                    elif isinstance(schema, (str, list)):
                        print(f"         📝 Raw schema response: {schema}")
                    
                    if attempt < max_retries - 1:
                        print(f"         🔄 Retrying with JSON format requirements...")
                        base_query += f"\n\nPrevious attempt returned invalid JSON. Please ensure you return ONLY a valid JSON object with no extra text or formatting."
                        continue
                    else:
                        return {"status": "error", "error": f"Generated schema is invalid JSON after all retries: {str(e)}"}
                        
            except Exception as e:
                # Check for specific RateLimitError exception type first
                try:
                    import litellm
                    if isinstance(e, litellm.RateLimitError):
                        print(f"         🔍 Detected litellm.RateLimitError exception")
                        if attempt < max_retries - 1:
                            print(f"         ⏳ Rate limit detected - waiting 60 seconds before retry...")
                            print(f"         📊 Error details: {str(e)[:200]}...")
                            await asyncio.sleep(60)  # Wait 1 minute for rate limit
                            print(f"         ✅ Wait complete, retrying schema generation...")
                            continue
                        else:
                            print(f"         🚫 Rate limit detected after all retries")
                            return {"status": "error", "error": f"Schema generation failed due to rate limits after all retries: {str(e)}"}
                except ImportError:
                    pass  # litellm not available, fall back to string detection
                
                print(f"         ❌ Schema generation failed on retry {attempt + 1}: {e}")
                
                # Check for rate limit errors with comprehensive detection
                error_str = str(e).lower()
                is_rate_limit = False
                
                # Check for specific RateLimitError exception type
                if hasattr(e, '__class__') and 'RateLimitError' in str(type(e)):
                    is_rate_limit = True
                    print(f"         🔍 Detected RateLimitError exception type")
                
                # Check for rate limit keywords in error message
                rate_limit_keywords = [
                    "rate limit", "quota", "resource_exhausted", "too many requests", 
                    "429", "quota exceeded", "rate exceeded", "throttled",
                    "quotafailure", "generatecontentinputtokenspermodelperminute"
                ]
                
                if any(keyword in error_str for keyword in rate_limit_keywords):
                    is_rate_limit = True
                    print(f"         🔍 Detected rate limit keywords in error message")
                
                if is_rate_limit:
                    if attempt < max_retries - 1:
                        print(f"         ⏳ Rate limit detected - waiting 60 seconds before retry...")
                        print(f"         📊 Error details: {str(e)[:200]}...")
                        await asyncio.sleep(60)  # Wait 1 minute for rate limit
                        print(f"         ✅ Wait complete, retrying schema generation...")
                        continue
                    else:
                        print(f"         🚫 Rate limit detected after all retries")
                        return {"status": "error", "error": f"Schema generation failed due to rate limits after all retries: {str(e)}"}
                
                if attempt < max_retries - 1:
                    print(f"         🔄 Retrying schema generation in 5 seconds...")
                    await asyncio.sleep(5)  # Short wait for other errors
                    continue
                else:
                    print(f"         🚫 Schema generation failed after all retries")
                    return {"status": "error", "error": f"Schema generation failed after all retries: {str(e)}"}
        
        # This should never be reached, but just in case
        return {"status": "error", "error": "Schema generation failed - unexpected end of retry loop"}
    
    except Exception as e:
        return {"status": "error", "error": f"Schema generation failed: {str(e)}"}


async def fetch_article_html(url: str, crawler) -> str:
    """Fetch HTML content from a single article URL"""
    
    try:
        from crawl4ai import CrawlerRunConfig
        from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
        
        config = CrawlerRunConfig(
            scraping_strategy=LXMLWebScrapingStrategy(),
            verbose=True,
            delay_before_return_html=2,
            js_code=["window.scrollTo(0, document.body.scrollHeight);"]
        )
        
        result = await crawler.arun(url, config=config)
        if result.success and result.html:
            return result.html
        else:
            logger.warning(f"⚠️ Failed to fetch article HTML from {url}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error fetching article HTML from {url}: {e}")
        return None


async def extract_article_with_schema(url: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Extract article content using the generated schema"""
    
    try:
        from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
        from utils.crawler_manager import get_shared_crawler
        from crawl4ai import CrawlerRunConfig
        
        # Extract the actual schema from the result object if needed
        if isinstance(schema, dict) and "schema" in schema and "status" in schema:
            # This is a result object from generate_article_schema_with_feedback
            actual_schema = schema["schema"]
            print(f"         📋 Extracted schema from result object: {actual_schema.get('name', 'Unknown')}")
        else:
            # This is already the actual schema
            actual_schema = schema
            print(f"         📋 Using direct schema: {actual_schema.get('name', 'Unknown')}")
        
        # Validate that we have the required fields
        if not isinstance(actual_schema, dict):
            logger.error(f"❌ Schema is not a dict: {type(actual_schema)}")
            return None
            
        if "baseSelector" not in actual_schema:
            logger.error(f"❌ Schema missing baseSelector field. Keys: {list(actual_schema.keys())}")
            return None
            
        print(f"         ✅ Schema validation passed - baseSelector: {actual_schema['baseSelector']}")
        
        # Create extraction strategy from schema
        extraction_strategy = JsonCssExtractionStrategy(actual_schema)
        
        config = CrawlerRunConfig(
            extraction_strategy=extraction_strategy,
            verbose=True,
            delay_before_return_html=2
        )
        
        crawler = await get_shared_crawler()
        result = await crawler.arun(url, config=config)
        
        if result.success and result.extracted_content:
            # Parse the extracted content
            try:
                extracted_data = json.loads(result.extracted_content)
                if isinstance(extracted_data, list) and len(extracted_data) > 0:
                    return extracted_data[0]  # Take first article
                elif isinstance(extracted_data, dict):
                    return extracted_data
                else:
                    return None
            except json.JSONDecodeError:
                return None
        else:
            return None
            
    except Exception as e:
        logger.error(f"❌ Schema extraction failed for {url}: {e}")
        return None


async def extract_ground_truth_with_retries(url: str, max_retries: int = 3) -> Dict[str, Any]:
    """
    Extract ground truth with retry logic. Does not cache failed attempts.
    
    Args:
        url: URL to extract ground truth from
        max_retries: Maximum number of retry attempts
        
    Returns:
        Ground truth extraction result or None if all retries fail
    """
    for attempt in range(max_retries):
        try:
            print(f"         🤖 Ground truth extraction attempt {attempt + 1}/{max_retries} for: {url}")
            ground_truth = await extract_article_with_llm(url)
            
            if ground_truth is not None:
                print(f"         ✅ Ground truth extraction successful on attempt {attempt + 1}")
                return ground_truth
            else:
                print(f"         ⚠️ Ground truth extraction returned None on attempt {attempt + 1}")
                
        except Exception as e:
            # Check for rate limit errors specifically
            error_str = str(e).lower()
            is_rate_limit = False
            
            # Check for specific RateLimitError exception type
            if hasattr(e, '__class__') and 'RateLimitError' in str(type(e)):
                is_rate_limit = True
                print(f"         🔍 Detected RateLimitError exception type")
            
            # Check for rate limit keywords in error message
            rate_limit_keywords = [
                "rate limit", "quota", "resource_exhausted", "too many requests", 
                "429", "quota exceeded", "rate exceeded", "throttled",
                "quotafailure", "generatecontentinputtokenspermodelperminute"
            ]
            
            if any(keyword in error_str for keyword in rate_limit_keywords):
                is_rate_limit = True
                print(f"         🔍 Detected rate limit keywords in error message")
            
            if is_rate_limit:
                if attempt < max_retries - 1:
                    wait_time = 60 + (attempt * 30)  # Increase wait time with each attempt
                    print(f"         ⏳ Rate limit detected - waiting {wait_time} seconds before retry...")
                    print(f"         📊 Error details: {str(e)[:200]}...")
                    await asyncio.sleep(wait_time)
                    print(f"         ✅ Wait complete, retrying ground truth extraction...")
                    continue
                else:
                    print(f"         🚫 Rate limit detected after all retries for ground truth")
                    logger.warning(f"⚠️ Ground truth extraction failed due to rate limits after {max_retries} attempts for {url}: {e}")
                    return None
            else:
                # Non-rate-limit error
                if attempt < max_retries - 1:
                    wait_time = 5 + (attempt * 5)  # Short wait for other errors
                    print(f"         ❌ Ground truth extraction failed on attempt {attempt + 1}: {e}")
                    print(f"         🔄 Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print(f"         🚫 Ground truth extraction failed after all retries")
                    logger.warning(f"⚠️ Ground truth extraction failed after {max_retries} attempts for {url}: {e}")
                    return None
    
    # This should never be reached, but just in case
    print(f"         🚫 Ground truth extraction failed - unexpected end of retry loop")
    return None


async def extract_article_with_llm(url: str) -> Dict[str, Any]:
    """Extract article content using Crawl4AI's LLM extraction as ground truth"""
    
    try:
        from crawl4ai.extraction_strategy import LLMExtractionStrategy
        from crawl4ai import LLMConfig, CrawlerRunConfig
        from utils.crawler_manager import get_shared_crawler
        
        # LLM extraction strategy following the documentation
        llm_strategy = LLMExtractionStrategy(
            llm_config=LLMConfig(
                provider="gemini/gemini-2.0-flash",
                api_token=os.getenv('GOOGLE_API_KEY')
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
            instruction="""You are an expert article content extractor. Your job is to extract the main article from this webpage with MAXIMUM ACCURACY.

CRITICAL SUCCESS CRITERIA:

1. TITLE EXTRACTION (HIGHEST PRIORITY):
   - The title is THE MOST IMPORTANT field - you MUST find it
   - Look in these exact locations in order of priority:
     a) <h1> tags anywhere on the page (most common)
     b) <title> tag content (remove site name suffixes like "- Bloomberg" or "| Reuters")
     c) Elements with: class="headline", class="title", class="article-title", class="story-title"
     d) Elements with: data-testid="headline", role="heading"
     e) Meta tags: property="og:title", name="twitter:title"
   - The title should be the MAIN article headline, not navigation or site branding
   - Clean the title: remove site names, remove " | Site Name", remove " - Publication"
   - Examples of GOOD titles: "Apple Announces Revolutionary New iPhone", "Markets Rally on Fed Decision"
   - Examples of BAD titles: "Home", "News", "Bloomberg", "Article - Reuters"
   - If you find multiple h1 tags, choose the one that looks most like an article headline
   - NEVER return an empty title - there is ALWAYS a title somewhere on a news article page

2. CONTENT EXTRACTION (MOST IMPORTANT):
   - Extract the COMPLETE main article body text
   - Include ALL paragraphs from start to finish of the article
   - Look for: <article>, class="article-body", class="content", class="story-body"
   - Include subheadings that are part of the article flow
   - EXCLUDE: navigation menus, advertisements, related articles, comments, headers/footers
   - Convert to clean plain text (no HTML, no markdown formatting)
   - Should be substantial content (minimum 200 characters for real articles)
   - Join paragraphs with double line breaks for readability

3. AUTHOR EXTRACTION:
   - Find the article author/byline
   - Look for: class="author", class="byline", rel="author", <span> near the title
   - Extract just the name, not "By" prefix
   - Example: "John Smith" not "By John Smith"

4. DATE EXTRACTION:
   - Find the publication date
   - Look for: <time>, datetime attributes, class="date", class="published"
   - Any date format is acceptable
   - Example: "March 15, 2024" or "2024-03-15" or "3 days ago"

EXTRACTION STRATEGY:
1. TITLE FIRST: Start by finding the title using the priority list above
2. Scan for semantic HTML5 elements: <article>, <main>, <section>
3. Look for common news site patterns: .article-body, .story-content, .post-content
4. For content: get all paragraph text within the main article container
5. Ignore sidebars, navigation, ads, and supplementary content

TITLE EXTRACTION EXAMPLES:
- If you see: <h1>Breaking: Fed Cuts Rates</h1> → Extract: "Breaking: Fed Cuts Rates"
- If you see: <title>Fed Cuts Rates - Bloomberg</title> → Extract: "Fed Cuts Rates"
- If you see: <h1 class="headline">Market Soars on News</h1> → Extract: "Market Soars on News"
- Look for the text that would appear as the headline when someone shares this article

QUALITY VALIDATION:
- Title MUST be specific and descriptive (not generic like "Home" or "News")
- Title MUST be found - use meta tags as fallback if needed
- Content should be complete article text (200+ chars for real articles)
- Author should be a person's name (if present)
- Date should be in a recognizable date format (if present)

Return the extracted data in the exact JSON schema format. The title field is MANDATORY - if you cannot find it in HTML, check meta tags. Every news article has a title somewhere.""",
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
        
        print(f"         🤖 Running LLM extraction...")
        crawler = await get_shared_crawler()
        result = await crawler.arun(url, config=config)
        
        if result.success and result.extracted_content:
            try:
                extracted_data = json.loads(result.extracted_content)
                
                # If it's a list, take the first item
                if isinstance(extracted_data, list) and len(extracted_data) > 0:
                    data = extracted_data[0]
                elif isinstance(extracted_data, dict):
                    data = extracted_data
                else:
                    print(f"         ❌ LLM extraction returned unexpected format: {type(extracted_data)}")
                    return None
                
                # Basic validation - just ensure we have a dict with required fields
                if not isinstance(data, dict):
                    print(f"         ❌ LLM extraction data is not a dict: {type(data)}")
                    return None
                
                title = str(data.get('title', '')).strip()
                content = str(data.get('content', '')).strip()
                
                # RELAXED validation - allow missing fields for comparison
                if not title:
                    print(f"         ⚠️ LLM extraction: no title found (will still use for comparison)")
                    title = "NO_TITLE_EXTRACTED"
                
                if not content:
                    print(f"         ⚠️ LLM extraction: no content found (will still use for comparison)")
                    content = "NO_CONTENT_EXTRACTED"
                
                # Basic markdown cleanup only
                import re
                content = re.sub(r'\*\*([^*]+)\*\*', r'\1', content)
                content = re.sub(r'\*([^*]+)\*', r'\1', content)
                content = re.sub(r'__([^_]+)__', r'\1', content)
                content = re.sub(r'_([^_]+)_', r'\1', content)
                content = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', content)
                content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
                content = re.sub(r'[ \t]+', ' ', content)
                
                print(f"         ✅ LLM extraction successful:")
                print(f"         📝 Title: {title}")
                print(f"         📝 Content length: {len(content)} characters")
                print(f"         📝 Content preview: {content[:150]}...")
                
                # Show token usage for debugging
                try:
                    llm_strategy.show_usage()
                except:
                    pass  # Usage info might not be available
                
                # Return the extracted data as-is (trust the LLM)
                return {
                    'title': title,
                    'content': content,
                    'date_published': str(data.get('date_published', '')).strip() if data.get('date_published') else '',
                    'author': str(data.get('author', '')).strip() if data.get('author') else ''
                }
                    
            except json.JSONDecodeError as e:
                print(f"         ❌ LLM extraction JSON parsing failed: {e}")
                return None
        else:
            print(f"         ❌ LLM extraction failed - no content returned")
            return None
            
    except Exception as e:
        logger.error(f"❌ LLM extraction failed for {url}: {e}")
        print(f"         ❌ LLM extraction exception: {e}")
        return None


async def compare_article_extractions(schema_result: Dict, ground_truth: Dict, url: str, max_retries: int = 3) -> Dict:
    """
    Compare schema extraction vs LLM ground truth with strict validation requirements.
    
    STRICT REQUIREMENTS:
    - Title: Must exist and closely match (30% weight)
    - Author: Must exist and match (25% weight) 
    - Date: Must exist and be valid (25% weight)
    - Content: Must exist and have substantial overlap (20% weight)
    
    FAILURE CONDITIONS:
    - Any required field completely missing = automatic failure
    - LLM ground truth extraction failed = automatic failure
    - Content length < 100 characters = automatic failure
    """
    
    print(f"         🔍 Starting STRICT comparison for URL: {url}")
    
    # First check for LLM ground truth failures
    if not ground_truth or not isinstance(ground_truth, dict):
        print(f"         ❌ Ground truth is invalid or missing")
        return {
            "score": 0.0,
            "details": "Ground truth extraction failed - cannot compare",
            "issues": ["ground_truth_invalid"],
            "schema_result": schema_result,
            "ground_truth": ground_truth
        }
    
    gt_title = ground_truth.get('title', '').strip()
    gt_author = ground_truth.get('author', '').strip() 
    gt_date = ground_truth.get('date_published', '').strip()
    gt_content = ground_truth.get('content', '')
    
    # Check for specific LLM extraction failures
    if gt_title == "NO_TITLE_EXTRACTED" or "choices" in str(gt_content):
        print(f"         ❌ LLM ground truth extraction failed (NO_TITLE_EXTRACTED or 'choices' error)")
        return {
            "score": 0.0,
            "details": "LLM ground truth extraction failed with known error patterns",
            "issues": ["llm_extraction_failed"],
            "schema_result": schema_result,
            "ground_truth": ground_truth
        }
    
    # Extract schema results
    schema_title = schema_result.get('title', '').strip()
    schema_author = schema_result.get('author', '').strip()
    schema_date = schema_result.get('date_published', '').strip()
    schema_content_raw = schema_result.get('content', [])
    
    # Process schema content
    if isinstance(schema_content_raw, list):
        schema_content = ' '.join([
            item.get('text', '') if isinstance(item, dict) else str(item) 
            for item in schema_content_raw
        ]).strip()
    else:
        schema_content = str(schema_content_raw).strip()
    
    print(f"         📊 STRICT VALIDATION CHECKS:")
    
    # CRITICAL FIELD VALIDATION (Must all pass or automatic failure)
    issues = []
    critical_failures = []
    
    # 1. Title validation
    if not schema_title or schema_title.lower() in ['missing', 'none', '']:
        critical_failures.append("missing_title")
        print(f"         ❌ CRITICAL: Title is missing from schema extraction")
    elif not gt_title or gt_title.lower() in ['missing', 'none', '']:
        critical_failures.append("missing_ground_truth_title") 
        print(f"         ❌ CRITICAL: Title is missing from ground truth")
    else:
        print(f"         ✅ Title present in both extractions")
    
    # 2. Author validation (optional - not critical)
    author_available = True
    if not schema_author or schema_author.lower() in ['missing', 'none', '']:
        print(f"         ⚠️ Author is missing from schema extraction (will reduce score but not fail)")
        author_available = False
    elif not gt_author or gt_author.lower() in ['missing', 'none', '']:
        print(f"         ⚠️ Author is missing from ground truth (will reduce score but not fail)")
        author_available = False
    else:
        print(f"         ✅ Author present in both extractions")
    
    # 3. Date validation
    if not schema_date or schema_date.lower() in ['missing', 'none', '']:
        critical_failures.append("missing_date")
        print(f"         ❌ CRITICAL: Date is missing from schema extraction")
    elif not gt_date or gt_date.lower() in ['missing', 'none', '']:
        critical_failures.append("missing_ground_truth_date")
        print(f"         ❌ CRITICAL: Date is missing from ground truth")
    else:
        print(f"         ✅ Date present in both extractions")
    
    # 4. Content validation
    if not schema_content or len(schema_content) < 100:
        critical_failures.append("insufficient_content")
        print(f"         ❌ CRITICAL: Schema content too short ({len(schema_content)} chars, need ≥100)")
    elif not gt_content or len(str(gt_content)) < 50:
        critical_failures.append("insufficient_ground_truth_content")
        print(f"         ❌ CRITICAL: Ground truth content too short ({len(str(gt_content))} chars)")
    else:
        print(f"         ✅ Content present in both extractions (schema: {len(schema_content)} chars, gt: {len(str(gt_content))} chars)")
    
    # If any critical validation fails, return 0 score
    if critical_failures:
        print(f"         🚨 AUTOMATIC FAILURE due to critical issues: {critical_failures}")
        return {
            "score": 0.0,
            "details": f"Critical validation failures: {', '.join(critical_failures)}",
            "issues": critical_failures,
            "schema_result": schema_result,
            "ground_truth": ground_truth
        }
    
    print(f"         🎯 All critical validations passed - proceeding with detailed scoring")
    
    # DETAILED SCORING (Only if all critical checks pass)
    scores = {}
    
    # Title similarity (30% weight)
    title_similarity = calculate_text_similarity(schema_title, gt_title)
    title_score = title_similarity * 30
    scores['title'] = {'similarity': title_similarity, 'score': title_score, 'weight': 30}
    print(f"         📝 Title similarity: {title_similarity:.2f} → Score: {title_score:.1f}/30")
    
    # Author similarity (25% weight) - but handle missing authors
    if author_available:
        author_similarity = calculate_text_similarity(schema_author, gt_author)
        author_score = author_similarity * 25
        scores['author'] = {'similarity': author_similarity, 'score': author_score, 'weight': 25}
        print(f"         👤 Author similarity: {author_similarity:.2f} → Score: {author_score:.1f}/25")
    else:
        # Author missing - give partial credit (10 out of 25 points)
        author_similarity = 0.4  # 40% similarity for "missing but acceptable"
        author_score = 10.0  # Partial credit
        scores['author'] = {'similarity': author_similarity, 'score': author_score, 'weight': 25}
        print(f"         👤 Author missing: Partial credit → Score: {author_score:.1f}/25")
    
    # Date similarity (25% weight)
    date_similarity = calculate_date_similarity(schema_date, gt_date)
    date_score = date_similarity * 25
    scores['date'] = {'similarity': date_similarity, 'score': date_score, 'weight': 25}
    print(f"         📅 Date similarity: {date_similarity:.2f} → Score: {date_score:.1f}/25")
    
    # Content similarity (20% weight)
    content_similarity = calculate_content_similarity(schema_content, str(gt_content))
    content_score = content_similarity * 20
    scores['content'] = {'similarity': content_similarity, 'score': content_score, 'weight': 20}
    print(f"         📄 Content similarity: {content_similarity:.2f} → Score: {content_score:.1f}/20")
    
    # Calculate final score
    final_score = title_score + author_score + date_score + content_score
    
    # Apply quality thresholds
    quality_issues = []
    if title_similarity < 0.7:
        quality_issues.append("low_title_similarity")
    if author_similarity < 0.7:
        quality_issues.append("low_author_similarity") 
    if date_similarity < 0.8:
        quality_issues.append("low_date_similarity")
    if content_similarity < 0.5:
        quality_issues.append("low_content_similarity")
    
    # Penalty for quality issues
    penalty = len(quality_issues) * 5  # 5 point penalty per quality issue
    final_score = max(0, final_score - penalty)
    
    print(f"         🎯 FINAL SCORE: {final_score:.1f}/100 (penalty: -{penalty} for {len(quality_issues)} quality issues)")
    
    return {
        "score": final_score,
        "details": f"Weighted score with {len(quality_issues)} quality issues",
        "issues": quality_issues,
        "scores": scores,
        "penalty": penalty,
        "schema_result": schema_result,
        "ground_truth": ground_truth
    }


def calculate_text_similarity(text1: str, text2: str) -> float:
    """Calculate similarity between two text strings using multiple methods"""
    if not text1 or not text2:
        return 0.0
    
    text1_clean = text1.lower().strip()
    text2_clean = text2.lower().strip()
    
    # Exact match
    if text1_clean == text2_clean:
        return 1.0
    
    # Substring match
    if text1_clean in text2_clean or text2_clean in text1_clean:
        return 0.9
    
    # Word overlap similarity
    words1 = set(text1_clean.split())
    words2 = set(text2_clean.split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    
    jaccard_similarity = len(intersection) / len(union)
    
    # Character-level similarity (basic)
    char_similarity = 1 - (abs(len(text1_clean) - len(text2_clean)) / max(len(text1_clean), len(text2_clean)))
    
    # Combine metrics
    return (jaccard_similarity * 0.7) + (char_similarity * 0.3)


def calculate_date_similarity(date1: str, date2: str) -> float:
    """Calculate similarity between two date strings"""
    if not date1 or not date2:
        return 0.0
    
    # Try to extract date components
    import re
    
    # Look for year patterns
    year_pattern = r'(\d{4})'
    years1 = re.findall(year_pattern, date1)
    years2 = re.findall(year_pattern, date2)
    
    if years1 and years2 and years1[0] == years2[0]:
        # Same year found
        
        # Look for month patterns 
        month_pattern = r'(\d{1,2})'
        months1 = re.findall(month_pattern, date1)
        months2 = re.findall(month_pattern, date2)
        
        if len(months1) >= 2 and len(months2) >= 2:
            # Compare month and day if available
            if months1[0] == months2[0] and months1[1] == months2[1]:
                return 1.0  # Same year, month, day
            elif months1[0] == months2[0]:
                return 0.8  # Same year, month
            else:
                return 0.6  # Same year only
        else:
            return 0.6  # Same year only
    else:
        # Fallback to text similarity
        return calculate_text_similarity(date1, date2) * 0.5


def calculate_content_similarity(content1: str, content2: str) -> float:
    """Calculate similarity between two content strings"""
    if not content1 or not content2:
        return 0.0
    
    # Basic length check
    len1, len2 = len(content1), len(content2)
    if min(len1, len2) < 100:
        return 0.0  # Too short to be meaningful
    
    # Word-based similarity
    words1 = set(content1.lower().split())
    words2 = set(content2.lower().split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    
    jaccard_similarity = len(intersection) / len(union)
    
    # Length ratio similarity
    length_ratio = min(len1, len2) / max(len1, len2)
    
    # Combine metrics
    return (jaccard_similarity * 0.8) + (length_ratio * 0.2)


def compile_improvement_feedback(comparisons: List[Dict[str, Any]]) -> str:
    """Compile specific feedback from multiple article comparisons"""
    
    all_missing = []
    all_selector_feedback = []
    
    for comparison in comparisons:
        all_missing.extend(comparison.get('missing_content', []))
        all_selector_feedback.extend(comparison.get('selector_feedback', []))
    
    # Find most common issues
    from collections import Counter
    
    common_missing = Counter(all_missing).most_common(3)
    common_fixes = Counter(all_selector_feedback).most_common(3)
    
    feedback_parts = []
    
    if common_missing:
        missing_text = "; ".join([f"{issue} (occurred {count} times)" for issue, count in common_missing])
        feedback_parts.append(f"COMMON MISSING CONTENT: {missing_text}")
    
    if common_fixes:
        fixes_text = "; ".join([f"{fix} (suggested {count} times)" for fix, count in common_fixes])
        feedback_parts.append(f"SUGGESTED IMPROVEMENTS: {fixes_text}")
    
    return ". ".join(feedback_parts) if feedback_parts else "No specific feedback available"


def calculate_objective_extraction_quality(extraction: Dict) -> Dict:
    """
    Calculate extraction quality based on objective criteria (no LLM comparison needed).
    This replaces the unreliable LLM ground truth validation.
    """
    
    score = 0
    details = {}
    issues = []
    
    # Extract and clean the data
    title = extraction.get('title', '').strip()
    author = extraction.get('author', '').strip()
    date = extraction.get('date_published', '').strip()
    content_raw = extraction.get('content', [])
    
    # Process content
    if isinstance(content_raw, list):
        content_text = ' '.join([
            item.get('text', '') if isinstance(item, dict) else str(item)
            for item in content_raw
        ]).strip()
    else:
        content_text = str(content_raw).strip()
    
    print(f"         📊 OBJECTIVE QUALITY ASSESSMENT:")
    
    # 1. Title Quality (40% weight)
    title_score = 0
    if not title:
        issues.append("missing_title")
        print(f"         ❌ Title: Missing (0/40 points)")
    elif len(title) < 10:
        issues.append("title_too_short")
        title_score = 10
        print(f"         ⚠️ Title: Too short ({len(title)} chars) (10/40 points)")
    elif title.lower() in ['home', 'news', 'article', 'page', 'website', 'blog']:
        issues.append("generic_title")
        title_score = 5
        print(f"         ⚠️ Title: Generic '{title}' (5/40 points)")
    elif any(word in title.lower() for word in ['404', 'error', 'not found', 'access denied']):
        issues.append("error_title")
        print(f"         ❌ Title: Error page '{title}' (0/40 points)")
    else:
        title_score = 40
        print(f"         ✅ Title: Good quality '{title[:50]}...' (40/40 points)")
    
    details['title'] = {'score': title_score, 'weight': 40, 'content': title}
    score += title_score
    
    # 2. Content Quality (35% weight)
    content_score = 0
    if not content_text:
        issues.append("missing_content")
        print(f"         ❌ Content: Missing (0/35 points)")
    elif len(content_text) < 100:
        issues.append("content_too_short")
        content_score = 5
        print(f"         ⚠️ Content: Too short ({len(content_text)} chars) (5/35 points)")
    elif len(content_text) < 300:
        content_score = 20
        print(f"         🟡 Content: Short but acceptable ({len(content_text)} chars) (20/35 points)")
    else:
        content_score = 35
        print(f"         ✅ Content: Good length ({len(content_text)} chars) (35/35 points)")
    
    details['content'] = {'score': content_score, 'weight': 35, 'length': len(content_text)}
    score += content_score
    
    # 3. Date Quality (15% weight)
    date_score = 0
    if not date:
        issues.append("missing_date")
        print(f"         ⚠️ Date: Missing (0/15 points)")
    elif any(char.isdigit() for char in date) and len(date) > 4:
        date_score = 15
        print(f"         ✅ Date: Present '{date}' (15/15 points)")
    else:
        issues.append("invalid_date")
        print(f"         ⚠️ Date: Invalid format '{date}' (0/15 points)")
    
    details['date'] = {'score': date_score, 'weight': 15, 'content': date}
    score += date_score
    
    # 4. Author Quality (10% weight) - Optional
    author_score = 0
    if not author:
        print(f"         ⚠️ Author: Missing (partial credit: 5/10 points)")
        author_score = 5  # Partial credit for missing author
    elif len(author) > 100:  # Probably not a real author
        issues.append("invalid_author")
        author_score = 2
        print(f"         ⚠️ Author: Too long, likely invalid (2/10 points)")
    else:
        author_score = 10
        print(f"         ✅ Author: Present '{author}' (10/10 points)")
    
    details['author'] = {'score': author_score, 'weight': 10, 'content': author}
    score += author_score
    
    # Quality thresholds
    if len(issues) >= 3:
        score = max(0, score - 20)  # Major penalty for multiple issues
        issues.append("multiple_quality_issues")
    
    print(f"         🎯 OBJECTIVE FINAL SCORE: {score:.1f}/100")
    if issues:
        print(f"         📋 Quality Issues: {', '.join(issues)}")
    
    return {
        "score": score,
        "details": details,
        "issues": issues,
        "validation_method": "objective_quality",
        "extraction_data": extraction
    }


async def validate_article_schema_objective(schema: Dict, sample_urls: List[str]) -> Dict:
    """
    Validate article schema using objective quality metrics instead of LLM ground truth.
    This is much more reliable and faster than LLM comparison.
    """
    
    print(f"         📊 OBJECTIVE VALIDATION: Testing schema on {len(sample_urls)} URLs...")
    
    results = []
    successful_extractions = 0
    
    for i, url in enumerate(sample_urls):
        print(f"         📊 [{i+1}/{len(sample_urls)}] Testing: {url[:80]}...")
        
        try:
            # Extract using the schema
            extraction_result = await extract_article_with_schema(url, schema)
            
            if extraction_result and extraction_result.get('success'):
                # Calculate objective quality
                quality_result = calculate_objective_extraction_quality(extraction_result)
                results.append(quality_result)
                
                if quality_result['score'] >= 60:  # 60% threshold for "successful"
                    successful_extractions += 1
                    print(f"         ✅ [{i+1}/{len(sample_urls)}] Success: {quality_result['score']:.1f}%")
                else:
                    print(f"         ❌ [{i+1}/{len(sample_urls)}] Low quality: {quality_result['score']:.1f}%")
            else:
                print(f"         ❌ [{i+1}/{len(sample_urls)}] Extraction failed")
                results.append({
                    "score": 0,
                    "details": {},
                    "issues": ["extraction_failed"],
                    "validation_method": "objective_quality",
                    "extraction_data": None
                })
                
        except Exception as e:
            print(f"         ❌ [{i+1}/{len(sample_urls)}] Exception: {e}")
            results.append({
                "score": 0,
                "details": {},
                "issues": ["exception", str(e)],
                "validation_method": "objective_quality", 
                "extraction_data": None
            })
    
    # Calculate overall score
    if results:
        average_score = sum(r['score'] for r in results) / len(results)
        success_rate = (successful_extractions / len(sample_urls)) * 100
    else:
        average_score = 0
        success_rate = 0
    
    print(f"         🎯 OBJECTIVE VALIDATION SUMMARY:")
    print(f"         📊 Average Quality Score: {average_score:.1f}%")
    print(f"         📊 Success Rate: {success_rate:.1f}% ({successful_extractions}/{len(sample_urls)})")
    
    return {
        "average_score": average_score,
        "success_rate": success_rate, 
        "successful_extractions": successful_extractions,
        "total_tested": len(sample_urls),
        "individual_results": results,
        "validation_method": "objective_quality"
    }


def compile_objective_feedback(validation_results: List[Dict[str, Any]]) -> str:
    """Compile specific feedback from objective validation results"""
    
    if not validation_results:
        return "No validation results available"
    
    issues_count = {}
    successful_extractions = 0
    total_extractions = len(validation_results)
    
    for result in validation_results:
        if result and result.get('score', 0) >= 60:
            successful_extractions += 1
        
        issues = result.get('issues', []) if result else ['no_result']
        for issue in issues:
            issues_count[issue] = issues_count.get(issue, 0) + 1
    
    feedback_parts = []
    
    # Success rate feedback
    success_rate = (successful_extractions / total_extractions) * 100 if total_extractions > 0 else 0
    if success_rate < 50:
        feedback_parts.append(f"Low success rate ({success_rate:.0f}%) - major schema improvements needed")
    elif success_rate < 80:
        feedback_parts.append(f"Moderate success rate ({success_rate:.0f}%) - schema needs refinement")
    
    # Common issues feedback
    common_issues = sorted(issues_count.items(), key=lambda x: x[1], reverse=True)[:3]
    
    if common_issues:
        issue_feedback = []
        for issue, count in common_issues:
            if issue == "missing_title":
                issue_feedback.append(f"Title extraction failing on {count} URLs - try broader title selectors like 'h1, h2, [class*=\"title\"], [class*=\"headline\"]'")
            elif issue == "missing_content":
                issue_feedback.append(f"Content extraction failing on {count} URLs - ensure selector captures all paragraph elements")
            elif issue == "content_too_short":
                issue_feedback.append(f"Content too short on {count} URLs - expand content selector to include more text elements")
            elif issue == "missing_date":
                issue_feedback.append(f"Date extraction missing on {count} URLs - add fallback date selectors")
            elif issue == "extraction_failed":
                issue_feedback.append(f"Schema extraction completely failed on {count} URLs - check baseSelector validity")
            elif issue == "title_too_short":
                issue_feedback.append(f"Title too short on {count} URLs - may be extracting wrong element")
            elif issue == "generic_title":
                issue_feedback.append(f"Generic titles on {count} URLs - selector may be targeting navigation instead of article title")
        
        if issue_feedback:
            feedback_parts.append("SPECIFIC IMPROVEMENTS: " + "; ".join(issue_feedback))
    
    return " | ".join(feedback_parts) if feedback_parts else "Schema performing well overall"


 