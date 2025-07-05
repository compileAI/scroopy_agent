import os, json, re, logging, textwrap
from typing import Dict, Any, Optional

import google.generativeai as genai

MODEL_NAME = "gemini-2.0-flash"
MAX_HTML_CHARS = 10000
API_KEY = os.getenv("GOOGLE_API_KEY")

logger = logging.getLogger(__name__)

def _coerce_to_json(obj: Any) -> Optional[Dict[str, Any]]:
    """
    Accept dict, JSON string, or Python-repr string and return a proper dict.
    """
    if isinstance(obj, dict):
        return obj

    if isinstance(obj, str):
        # Grab the first {...} or [...] block in case the model adds prose
        match = re.search(r'(\{.*\}|\[.*\])', obj, re.DOTALL)
        if match:
            snippet = match.group(1)
            try:
                return json.loads(snippet)
            except json.JSONDecodeError:
                try:
                    import ast
                    return ast.literal_eval(snippet)
                except Exception:
                    pass
    return None

def _merge_patch(old: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Smart merge for schema patches: merge fields by name, replace other arrays.
    """
    merged = old.copy()
    for k, v in patch.items():
        if k == "fields" and isinstance(v, list) and isinstance(old.get(k), list):
            # Special handling for fields array - merge by field name
            merged_fields = old[k].copy()
            logger.info(f"🔧 Merging fields: {len(merged_fields)} existing, {len(v)} patch fields")
            for patch_field in v:
                if isinstance(patch_field, dict) and "name" in patch_field:
                    # Find existing field with same name and update it
                    field_updated = False
                    for i, existing_field in enumerate(merged_fields):
                        if isinstance(existing_field, dict) and existing_field.get("name") == patch_field["name"]:
                            logger.info(f"🔄 Updating existing field '{patch_field['name']}'")
                            merged_fields[i] = {**existing_field, **patch_field}
                            field_updated = True
                            break
                    # If field not found, add it
                    if not field_updated:
                        logger.info(f"➕ Adding new field '{patch_field['name']}'")
                        merged_fields.append(patch_field)
            merged[k] = merged_fields
            logger.info(f"✅ Final field count: {len(merged_fields)}")
        elif isinstance(v, dict) and isinstance(old.get(k), dict):
            merged[k] = _merge_patch(old[k], v)
        else:
            merged[k] = v
    return merged

async def generate_schema(html_content: str) -> Optional[Dict[str, Any]]:
    """
    Ask Crawl4AI to build an initial CSS-based extraction schema with enhanced prompting.
    """

    from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
    from crawl4ai import LLMConfig
    
    # Enhanced prompt with few-shot examples and detailed instructions
    enhanced_query = """
You are an expert at creating CSS extraction schemas for news articles and blog posts.

CRITICAL: Return ONLY valid JSON. No markdown, no explanations, no extra text.

Your task is to analyze the HTML content and create a JSON schema for extracting:
- title: Article headline
- content: Main article text (as nested list of paragraphs)
- author: Article author(s) 
- date_published: Publication date

IMPORTANT REQUIREMENTS:
- Use CSS selectors that target the MAIN CONTENT areas ONLY
- AVOID navigation, ads, sidebars, comments, related articles, headers, footers
- Prefer class-based selectors over element tags
- Use "text" type for title, author, date_published
- Use "nested_list" type for content with paragraphs
- CRITICAL: Nested fields (like paragraph within content) should NOT have selectors - only the parent field has a selector
- Test selectors work for the content type (don't select empty elements)

CONTENT EXTRACTION STRATEGY:
- The "content" field MUST capture ONLY the main article text
- NEVER use "body p" or "body" as selectors - these are too broad
- Look for specific article containers like: article, .article, .post, .entry, .content, .article-body, .post-content
- Your selector should target paragraph elements WITHIN the article container
- Example selectors: "article p", ".article-body p", ".post-content p", ".entry-content p"
- If no specific container exists, use more specific selectors like "main p" or ".main-content p"
- The selector should be specific enough to avoid navigation or sidebar content

EXAMPLES OF GOOD SCHEMAS:

Meta AI Blog:
{
    "name": "Meta AI Blog Posts",
    "fields": [
        {"name": "title", "type": "text", "selector": "span._amgd"},
        {"name": "content", "type": "nested_list", "fields": [{"name": "text", "type": "text"}], "selector": "div._a5ci._a5cs._a92o._a5c-._a5w7 p"},
        {"name": "date_published", "type": "text", "selector": "span._amum"}
    ],
    "baseSelector": "body"
}

Space.com Article:
{
    "name": "Space.com Article",
    "fields": [
        {"name": "title", "type": "text", "selector": "header h1"},
        {"name": "content", "type": "nested_list", "fields": [{"name": "text", "type": "text"}], "selector": "#article-body p, #article-body h2, #article-body h3, #article-body h4, #article-body h5, #article-body h6, #article-body ul li, #article-body ol li, #article-body blockquote, #article-body q, #article-body pre, #article-body code, #article-body div.text, #article-body span.text"},
        {"name": "date_published", "type": "attribute", "selector": "header time", "attribute": "datetime"},
        {"name": "author", "type": "text", "selector": "header .byline a[rel='author']"}
    ],
    "baseSelector": "article.news-article"
}

Anthropic Blog:
{
    "name": "Anthropic Blog Posts", 
    "fields": [
        {"name": "title", "type": "text", "selector": "h1.h2"},
        {"name": "content", "type": "nested_list", "fields": [{"name": "text", "type": "text"}], "selector": "div.Body_body__XEXq7 p"},
        {"name": "date_published", "type": "text", "selector": "div.PostDetail_post-timestamp__TBJ0Z"}
    ],
    "baseSelector": "body"
}

KEY PATTERNS TO FOLLOW:
1. Title: Usually h1, h2, or class-based selectors like .headline, .title
2. Content: Use nested_list with broad selectors that capture all text elements
3. Date: Often time elements with datetime attribute, or class-based selectors
4. Author: Usually .author, .byline, [rel='author'], or near the title
5. BaseSelector: Often "body", "article", "main", or specific article containers

Return ONLY the JSON schema, nothing else.
"""
    
    try:
        schema_raw = JsonCssExtractionStrategy.generate_schema(
            html=html_content,
            llm_config=LLMConfig(
                provider="gemini/gemini-2.0-flash",
                api_token=API_KEY
            ),
            query=enhanced_query
        )
    except Exception as e:
        logger.error(f"❌ LLM call failed: {e}")
        return None

    schema = _coerce_to_json(schema_raw)
    if schema is None:
        logger.error("❌ Unable to coerce LLM output into JSON")
    return schema

async def extract_with_schema(url: str, schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Download `url` and apply the supplied schema.
    """
    try:
        from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
        from crawl4ai import CrawlerRunConfig
        from utils.crawler_manager import get_shared_crawler

        if not isinstance(schema, dict):
            logger.error("❌ Schema must be a dict")
            return None

        extraction_strategy = JsonCssExtractionStrategy(schema)

        config = CrawlerRunConfig(
            extraction_strategy=extraction_strategy,
            verbose=False,
            delay_before_return_html=2,
        )

        crawler = await get_shared_crawler()
        result = await crawler.arun(url, config=config)

        if result.success and result.extracted_content:
            data = _coerce_to_json(result.extracted_content)
            if isinstance(data, list):
                return data[0] if data else None
            return data

        logger.error(f"❌ Extraction failed: {getattr(result, 'error', 'unknown')}")
        return None

    except Exception as e:
        logger.error(f"❌ Schema extraction failed for {url}: {e}")
        return None

async def patch_schema_with_feedback(
    html: str,
    old_schema: Dict[str, Any],
    feedback: str,
    candidate_selectors: str,
    *,
    api_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Ask Gemini to revise `old_schema` given `feedback` and return an updated schema.
    Feedback should only describe one issue at a time.

    Returns None on failure.
    """
    api_token = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_token:
        logger.error("No GEMINI_API_KEY / GOOGLE_API_KEY present")
        return None

    genai.configure(api_key=api_token)
    model = genai.GenerativeModel(MODEL_NAME)

    context = textwrap.dedent(f"""
    TASK:
    You are a senior web-scraping engineer. Given:
      • HTML of a news article page (truncated below)
      • The CURRENT JSON extraction schema (follows Crawl4AI format)
      • Human feedback about what is missing or wrong
      • Candidate selectors to consider
    Return ONLY a VALID JSON **schema patch** object that, when merged into the current
    schema, fixes the issue. Do not output explanations or markdown.

    CRITICAL OUTPUT FORMAT:
      Return a JSON object with the same structure as the current schema, but only include
      the fields you want to modify. For example:
      {{
        "fields": [
          {{"name": "title", "type": "text", "selector": "h1"}},
          {{"name": "content", "type": "nested_list", "fields": [{{"name": "text", "type": "text"}}], "selector": ".entry-content p"}}
        ]
      }}
      
      DO NOT use JSON Patch format (no "op", "path", "value" fields).

    CRITICAL RULES:
      • Prefer CSS selectors that target ARTICLE BODY not nav/ads/comments
      • Keep existing selectors that still work; modify only broken ones
      • If you cannot fix a field, omit it from the patch
      • Use "nested_list" type for content with proper structure
      • Nested fields should NOT have selectors - only parent field has selector
      • Content selectors should capture ONLY main article text
      • Rarely use "body p" or "body" as selectors - these are often too broad
      • Look for specific article containers: article, .article, .post, .entry, .content, .article-body, .post-content

    COMMON SELECTOR PATTERNS:
      • Title: h1, h2, .headline, .title, [class*="title"], [class*="headline"]
      • Content: .content p, .article-body p, .post-content p, [class*="content"] p
      • Author: .author, .byline, [rel="author"], .post-author, .entry-author
      • Date: time[datetime], .date, .published, .entry-date, [class*="date"]

    EXAMPLES OF GOOD FIELD STRUCTURES:
      Title: {{"name": "title", "type": "text", "selector": "h1, .headline"}}
      Content: {{"name": "content", "type": "nested_list", "fields": [{{"name": "text", "type": "text"}}], "selector": "article p, article h2, article h3"}}
      Author: {{"name": "author", "type": "text", "selector": ".author, .byline"}}
      Date: {{"name": "date_published", "type": "text", "selector": "time, .date"}}

    --- FEEDBACK ---
    {feedback}

    --- HTML (first {MAX_HTML_CHARS} chars) ---
    {html[:MAX_HTML_CHARS]}

    --- CANDIDATE SELECTORS ---
    {candidate_selectors}

    --- CURRENT_SCHEMA_JSON ---
    {json.dumps(old_schema, indent=2)}
    """)

    try:
        response = model.generate_content(context, safety_settings={"HARASSMENT":"block_none"})
        raw = response.text.strip()
        logger.info(f"🔍 Gemini response: {raw[:200]}...")
    except Exception as e:
        logger.error(f"Gemini call failed: {e}")
        return None

    try:
        patch_obj = json.loads(raw)
        logger.info(f"✅ Parsed patch object: {json.dumps(patch_obj, indent=2)}")
    except json.JSONDecodeError:
        # Sometimes model wraps JSON in ``` or prose—extract inside {...}
        try:
            snippet = re.search(r'(\{.*\})', raw, re.S).group(1)
            patch_obj = json.loads(snippet)
            logger.info(f"✅ Parsed patch from snippet: {json.dumps(patch_obj, indent=2)}")
        except Exception:
            logger.error(f"Could not parse Gemini output:\n{raw[:300]}…")
            return None

    if not isinstance(patch_obj, dict):
        logger.error("Patch is not a JSON object")
        return None

    return _merge_patch(old_schema, patch_obj)
