"""
Enhanced Article schema generation tool with improved feedback integration for LangGraph
"""

import json
import logging
import os
from typing import Dict, List, Any, Optional
from urllib.parse import urljoin, urlparse
import asyncio

# Import base functionality from the original module
from tools.article_schema_generator import (
    get_source_name_from_url,
    normalize_url,
    check_source_exists,
    fetch_article_html,
    extract_article_with_schema,
    extract_ground_truth_with_retries,
    compare_article_extractions,
    calculate_text_similarity,
    calculate_date_similarity,
    calculate_content_similarity
)

logger = logging.getLogger(__name__)

async def generate_validated_article_schema_with_feedback(
    base_url: str, 
    sample_urls: List[str], 
    validation_feedback: Optional[List[str]] = None,
    ground_truth_cache: Optional[Dict[str, Any]] = None,
    previous_schema: Optional[Dict] = None
) -> str:
    """
    Enhanced article schema generation that incorporates validation feedback
    
    Args:
        base_url: The base URL of the news source
        sample_urls: List of sample article URLs to test against
        validation_feedback: List of feedback strings from previous attempts
        ground_truth_cache: Cache of ground truth extractions to avoid re-extraction
        
    Returns:
        JSON string with validation results and schema
    """
    logger.info(f"🎯 Enhanced article schema generation for {base_url}")
    
    if validation_feedback:
        logger.info(f"🔄 Using validation feedback: {'; '.join(validation_feedback)}")
    
    if not sample_urls or len(sample_urls) < 2:
        return json.dumps({
            "status": "error",
            "error": "Need at least 2 sample URLs for validation",
            "validation_score": 0,
            "attempts": 0
        })
    
    # Use provided cache or create new one
    if ground_truth_cache is None:
        ground_truth_cache = {}
    
    # Single attempt only - retries handled by LangGraph
    attempt = 1
    logger.info(f"🔄 Single attempt schema generation")
    
    try:
        # Step 1: Generate schema with enhanced feedback integration
        schema = await generate_article_schema_with_enhanced_feedback(
            base_url, 
            sample_urls, 
            validation_feedback, 
            attempt,
            previous_schema
        )
        
        if not schema:
            logger.error(f"❌ Schema generation failed")
            return json.dumps({
                "status": "error",
                "error": "Schema generation failed",
                "validation_score": 0,
                "attempt": attempt
            })
            
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
        
        # Step 3: Enhanced LLM Ground Truth Validation with better comparison
        print(f"         📊 Step 3: ENHANCED LLM VALIDATION - Testing schema on {len(sample_urls)} URLs...")
        
        comparisons = []
        validation_scores = []
        
        for i, url in enumerate(sample_urls):
            print(f"         🔍 [{i+1}/{len(sample_urls)}] Comparing against ground truth: {url[:80]}...")
            
            try:
                # Get ground truth using LLM extraction (with caching)
                if url in ground_truth_cache:
                    ground_truth = ground_truth_cache[url]
                    print(f"         ♻️ [{i+1}/{len(sample_urls)}] Using cached ground truth")
                else:
                    ground_truth = await extract_ground_truth_with_retries(url)
                    ground_truth_cache[url] = ground_truth
                
                if not ground_truth:
                    print(f"         ❌ [{i+1}/{len(sample_urls)}] Ground truth extraction failed")
                    comparisons.append({
                        "url": url,
                        "comparison_status": "failed",
                        "completeness_score": 0,
                        "error": "Ground truth extraction failed"
                    })
                    validation_scores.append(0)
                    continue
                
                # Enhanced comparison with better feedback generation
                schema_result = schema_extractions[i] if i < len(schema_extractions) else None
                if schema_result:
                    comparison = await compare_article_extractions_enhanced(
                        schema_result, 
                        ground_truth, 
                        url,
                        validation_feedback  # Pass feedback to improve comparison
                    )
                    comparisons.append(comparison)
                    
                    score = comparison.get("completeness_score", 0)
                    validation_scores.append(score)
                    
                    print(f"         📊 [{i+1}/{len(sample_urls)}] Comparison score: {score:.1f}%")
                    print(f"         💬 [{i+1}/{len(sample_urls)}] Assessment: {comparison.get('overall_assessment', 'N/A')}")
                    
                    # Show specific feedback
                    missing = comparison.get("missing_content", [])
                    if missing:
                        print(f"         ❌ [{i+1}/{len(sample_urls)}] Missing: {'; '.join(missing)}")
                        
                else:
                    print(f"         ❌ [{i+1}/{len(sample_urls)}] Schema extraction was None")
                    comparisons.append({
                        "url": url,
                        "comparison_status": "failed", 
                        "completeness_score": 0,
                        "error": "Schema extraction returned None"
                    })
                    validation_scores.append(0)
                    
            except Exception as e:
                logger.warning(f"⚠️ Comparison failed for {url}: {e}")
                print(f"         ❌ [{i+1}/{len(sample_urls)}] Comparison failed: {e}")
                comparisons.append({
                    "url": url,
                    "comparison_status": "error",
                    "completeness_score": 0,
                    "error": str(e)
                })
                validation_scores.append(0)
        
        # Calculate overall validation score
        if validation_scores:
            overall_score = sum(validation_scores) / len(validation_scores)
        else:
            overall_score = 0.0
        
        logger.info(f"📊 Overall validation score: {overall_score:.1f}%")
        
        # Generate enhanced feedback for next iteration
        enhanced_feedback = generate_enhanced_validation_feedback(
            comparisons, 
            schema_extractions, 
            ground_truth_cache, 
            sample_urls
        )
        
        # Return results with enhanced feedback
        result = {
            "status": "success",
            "schema": schema,
            "validation_score": overall_score,
            "attempt": attempt,
            "comparisons": comparisons,
            "schema_extractions": schema_extractions,
            "ground_truth_extractions": [ground_truth_cache.get(url) for url in sample_urls],
            "sample_urls": sample_urls,
            "enhanced_feedback": enhanced_feedback
        }
        
        logger.info(f"✅ Single attempt completed. Score: {overall_score:.1f}%")
        return json.dumps(result)
                
    except Exception as e:
        logger.error(f"❌ Schema generation attempt failed: {e}")
        return json.dumps({
            "status": "error",
            "error": f"Schema generation failed: {str(e)}",
            "validation_score": 0,
            "attempt": attempt
        })

async def generate_article_schema_with_enhanced_feedback(
    homepage_url: str, 
    sample_urls: List[str], 
    validation_feedback: Optional[List[str]] = None,
    attempt: int = 1,
    previous_schema: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Generate article schema with enhanced feedback integration
    
    Args:
        homepage_url: URL of the news source homepage
        sample_urls: Sample article URLs for testing
        validation_feedback: Feedback from previous validation attempts
        attempt: Current attempt number
        
    Returns:
        Generated schema dictionary
    """
    from utils.crawler_manager import get_shared_crawler
    
    logger.info(f"🔧 Generating article schema with enhanced feedback (attempt {attempt})")
    
    try:
        # Get one sample article for schema generation
        test_url = sample_urls[0]
        
        # Fetch the article HTML
        crawler = await get_shared_crawler()
        result = await crawler.arun(url=test_url)
        
        if not result.success:
            logger.error(f"❌ Failed to fetch article: {test_url}")
            return None
        
        html_content = result.html
        if not html_content or len(html_content) < 100:
            logger.error(f"❌ No substantial content found in article: {test_url}")
            return None
        
        # Generate enhanced prompt that incorporates feedback
        enhanced_prompt = create_enhanced_schema_prompt(
            html_content, 
            homepage_url, 
            validation_feedback, 
            attempt,
            previous_schema
        )
        
        # Use LLM to generate schema
        api_key = os.getenv('GOOGLE_API_KEY')
        if not api_key:
            logger.error("❌ No GOOGLE_API_KEY found")
            return None
        
        from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
        from crawl4ai import LLMConfig
        
        schema = JsonCssExtractionStrategy.generate_schema(
            html=html_content,
            llm_config=LLMConfig(
                provider="gemini/gemini-2.0-flash",
                api_token=api_key
            ),
            query=enhanced_prompt
        )
        
        if isinstance(schema, list) and len(schema) > 0:
            schema_text = str(schema[0]).strip()
        else:
            schema_text = str(schema).strip()
        
        # Parse the schema
        try:
            schema_obj = json.loads(schema_text)
        except json.JSONDecodeError:
            # Try to convert Python dict syntax
            import ast
            try:
                schema_obj = ast.literal_eval(schema_text)
            except (ValueError, SyntaxError):
                logger.error(f"❌ Failed to parse schema: {schema_text[:200]}...")
                return None
        
        # Add source metadata
        schema_obj["source_url"] = homepage_url
        schema_obj["generated_from"] = test_url
        schema_obj["attempt"] = attempt
        
        return schema_obj
        
    except Exception as e:
        logger.error(f"❌ Error generating enhanced schema: {e}")
        return None

def create_enhanced_schema_prompt(
    html_content: str, 
    homepage_url: str, 
    validation_feedback: Optional[List[str]] = None,
    attempt: int = 1,
    previous_schema: Optional[Dict] = None
) -> str:
    """Create an enhanced prompt that incorporates validation feedback"""
    
    base_prompt = f"""
You are an expert at creating CSS extraction schemas for news articles. 

CRITICAL: Return ONLY valid JSON. No markdown, no explanations, no extra text.

Your task is to analyze this HTML content from a news article and create a JSON schema for extracting:
- title: Article headline
- content: Main article text (as array of paragraphs)
- author: Article author(s)
- date_published: Publication date

IMPORTANT REQUIREMENTS:
- Use CSS selectors that target the MAIN CONTENT areas
- Avoid navigation, ads, sidebars, comments, and related articles
- Prefer class-based selectors over element tags
- Use "text" type for title, author, date_published
- Use "nested_list" type for content with paragraphs
- CRITICAL: Nested fields (like paragraph within content) should NOT have selectors - only the parent field has a selector
- Test selectors work for the content type (don't select empty elements)

SCHEMA FORMAT:
{{
    "name": "Source Name Articles",
    "baseSelector": "article, .article, .post, .story",
    "fields": [
        {{
            "name": "title",
            "type": "text",
            "selector": "h1, .headline, .title"
        }},
        {{
            "name": "content", 
            "type": "nested_list",
            "selector": ".content p, .article-body p, .story-body p",
            "fields": [
                {{
                    "name": "text",
                    "type": "text"
                }}
            ]
        }},
        {{
            "name": "author",
            "type": "text", 
            "selector": ".author, .byline, [rel='author']"
        }},
        {{
            "name": "date_published",
            "type": "text",
            "selector": "time, .date, .published"
        }}
    ]
}}

Source: {urlparse(homepage_url).netloc}
"""

    # Add previous attempt context and feedback
    if previous_schema and validation_feedback:
        import json
        previous_schema_str = json.dumps(previous_schema, indent=2)
        feedback_text = "\n".join([f"- {fb}" for fb in validation_feedback])
        
        feedback_prompt = f"""

PREVIOUS SCHEMA ATTEMPT (that you tried):
{previous_schema_str}

VALIDATION RESULTS AND FEEDBACK:
{feedback_text}

CRITICAL IMPROVEMENT INSTRUCTIONS:
- Keep selectors that worked well (mentioned as successful in feedback)
- Fix ONLY the selectors that failed (mentioned as missing or incorrect)
- If feedback mentions "TITLE SELECTOR", update ONLY the title field selector
- If feedback mentions "CONTENT SELECTOR", update ONLY the content field selector  
- If feedback mentions "AUTHOR SELECTOR", update ONLY the author field selector
- If feedback mentions "DATE SELECTOR", update ONLY the date field selector
- If feedback says a field is working correctly, DO NOT change its selector
- Focus improvements on specific failing areas, not wholesale changes
"""
        base_prompt += feedback_prompt
    elif validation_feedback:
        feedback_text = "\n".join([f"- {fb}" for fb in validation_feedback])
        feedback_prompt = f"""

CRITICAL VALIDATION FEEDBACK - IMPLEMENT THESE EXACT IMPROVEMENTS:
{feedback_text}

IMPLEMENTATION RULES:
- If the feedback mentions a specific field being right, do not change the selectors.
"""
        base_prompt += feedback_prompt
    
    base_prompt += "\n\nReturn ONLY the JSON schema, nothing else."
    
    return base_prompt

async def compare_article_extractions_enhanced(
    schema_result: Dict, 
    ground_truth: Dict, 
    url: str,
    validation_feedback: Optional[List[str]] = None
) -> Dict:
    """
    Enhanced comparison that provides better feedback for schema improvement
    
    Args:
        schema_result: Result from CSS schema extraction
        ground_truth: Result from LLM extraction
        url: URL being compared
        validation_feedback: Previous feedback to avoid repetition
        
    Returns:
        Enhanced comparison results with specific improvement suggestions
    """
    try:
        from utils.llm_config import get_llm_config
        import google.generativeai as genai
        
        config = get_llm_config()
        if not config or not config.provider.startswith("gemini"):
            logger.error("❌ Enhanced comparison requires Gemini configuration")
            return {
                "comparison_status": "error",
                "completeness_score": 0,
                "error": "LLM configuration not available"
            }
        
        genai.configure(api_key=config.api_token)
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Create enhanced comparison prompt
        comparison_prompt = f"""
You are an expert at evaluating web extraction schemas. Compare these two extractions and provide specific feedback.

URL: {url}

SCHEMA EXTRACTION:
Title: {schema_result.get('title', 'MISSING')}
Author: {schema_result.get('author', 'MISSING')}
Date: {schema_result.get('date_published', 'MISSING')}
Content: {len(schema_result.get('content', []))} paragraphs

GROUND TRUTH (LLM):
Title: {ground_truth.get('title', 'MISSING')}
Author: {ground_truth.get('author', 'MISSING')}
Date: {ground_truth.get('date_published', 'MISSING')}
Content: {len(ground_truth.get('content', []))} paragraphs

EVALUATION CRITERIA:
1. Title accuracy (0-25 points)
2. Content completeness (0-50 points)
3. Author extraction (0-15 points)
4. Date extraction (0-10 points)

Return JSON with:
{{
    "completeness_score": <0-100>,
    "title_score": <0-25>,
    "content_score": <0-50>,
    "author_score": <0-15>,
    "date_score": <0-10>,
    "missing_content": ["list", "of", "missing", "elements"],
    "selector_feedback": ["specific", "css", "selector", "suggestions"],
    "overall_assessment": "Brief assessment of schema quality"
}}

Focus on specific, actionable feedback for CSS selector improvement.
"""

        # Add context about previous feedback to avoid repetition
        if validation_feedback:
            comparison_prompt += f"\n\nPREVIOUS FEEDBACK: {'; '.join(validation_feedback)}\nProvide NEW, different suggestions."
        
        response = model.generate_content(
            comparison_prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=1000,
                temperature=0.1
            )
        )
        
        response_text = response.text.strip()
        
        # Extract JSON from response
        import re
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            comparison_data = json.loads(json_match.group(0))
        else:
            # Fallback to basic comparison
            logger.warning("⚠️ Enhanced comparison failed, using basic comparison")
            return await compare_article_extractions(schema_result, ground_truth, url)
        
        # Add URL for tracking
        comparison_data["url"] = url
        comparison_data["comparison_status"] = "success"
        
        return comparison_data
        
    except Exception as e:
        logger.error(f"❌ Enhanced comparison error: {e}")
        # Fallback to basic comparison
        return await compare_article_extractions(schema_result, ground_truth, url)

def generate_enhanced_validation_feedback(
    comparisons: List[Dict], 
    schema_extractions: List[Dict], 
    ground_truth_cache: Dict,
    sample_urls: List[str]
) -> List[str]:
    """
    Generate specific, actionable feedback based on validation results
    
    Args:
        comparisons: List of comparison results
        schema_extractions: List of schema extraction results
        ground_truth_cache: Cache of ground truth extractions
        sample_urls: List of URLs tested
        
    Returns:
        List of specific feedback strings
    """
    feedback = []
    
    # Analyze patterns across all comparisons
    total_comparisons = len([c for c in comparisons if c.get("comparison_status") == "success"])
    
    if total_comparisons == 0:
        feedback.append("All extractions failed - use more specific baseSelector like '.post', '.entry', or main element containers")
        return feedback
    
    # Analyze common issues and generate VERY specific feedback
    title_issues = sum(1 for c in comparisons if c.get("title_score", 0) < 15)
    content_issues = sum(1 for c in comparisons if c.get("content_score", 0) < 20)
    author_issues = sum(1 for c in comparisons if c.get("author_score", 0) < 10)
    date_issues = sum(1 for c in comparisons if c.get("date_score", 0) < 10)
    
    # Generate ACTIONABLE feedback that can be directly used in prompts
    if title_issues > total_comparisons * 0.5:
        feedback.append("TITLE SELECTOR: Use 'h1.entry-title, h1.post-title, h1[class*=\"title\"], .headline h1' instead of generic h1")
    
    if content_issues > total_comparisons * 0.5:
        feedback.append("CONTENT SELECTOR: Use '.entry-content p, .post-content p, .article-content p, [class*=\"content\"] p' for paragraphs")
    
    if author_issues > total_comparisons * 0.5:
        feedback.append("AUTHOR SELECTOR: Use '.author .name, .byline .author, .post-author, [rel=\"author\"], .entry-author' for author names")
    
    if date_issues > total_comparisons * 0.5:
        feedback.append("DATE SELECTOR: Use 'time[datetime], .entry-date, .published-date, .post-date, [class*=\"date\"]' for publication dates")
    
    # Collect specific selector feedback from LLM comparisons
    for comparison in comparisons:
        selector_feedback = comparison.get("selector_feedback", [])
        for suggestion in selector_feedback:
            if suggestion not in feedback and "selector" in suggestion.lower():
                feedback.append(suggestion)
    
    # Add schema structure improvements
    if len([e for e in schema_extractions if e is None]) > len(schema_extractions) * 0.5:
        feedback.append("SCHEMA STRUCTURE: Try using 'main, article, .main-content, .post, .entry' as baseSelector instead of generic elements")
    
    # Limit feedback to most important items
    return feedback[:5]

# Convenience function that maintains compatibility
async def generate_validated_article_schema(base_url: str, sample_urls: List[str]) -> str:
    """
    Main function that can be called with or without feedback
    This maintains compatibility with existing code while enabling enhanced features
    """
    return await generate_validated_article_schema_with_feedback(base_url, sample_urls, None)
