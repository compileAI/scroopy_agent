from models.stagehand import LinkList, Article
from pydantic import ValidationError
import hashlib
import os
from typing import Optional, Any, List, Tuple, Union
from supabase import create_client, Client

# ---------- 1️⃣  Supabase Cache Backend -----------------------------------

def get_cache_client() -> Client:
    """Get Supabase client for cache operations"""
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables required")
    
    return create_client(supabase_url, supabase_key)


def url_hash(url: str) -> str:
    """Create a clean hash for URL-based cache keys"""
    return hashlib.md5(url.encode()).hexdigest()[:12]


def content_hash(content: str) -> str:
    """Create a hash of DOM content to detect changes"""
    return hashlib.md5(content.encode()).hexdigest()[:16]


def _parse_cache_type(key: str) -> Tuple[str, str]:
    """
    Parse cache key to determine type and url_hash.
    
    Returns: (cache_type, url_hash)
    """
    parts = key.split("_")
    
    if key.startswith("dom_hash_"):
        return ("dom_hash", parts[-1])
    elif key.startswith("last_link_"):
        return ("last_link", parts[-1])
    elif key.startswith("link_extraction_"):
        return ("link_extraction", parts[-1])
    elif key.startswith("article_extraction_"):
        return ("article_extraction", parts[-1])
    else:
        return ("other", "")


async def get_cache(key: str) -> Optional[Any]:
    """Get cached value for a key, returns None if not found"""
    try:
        supabase = get_cache_client()
        result = supabase.table('stagehand_cache').select('value').eq('key', key).execute()
        
        if not result.data or len(result.data) == 0:
            return None
        
        value = result.data[0]['value']
        
        # Unwrap simple values that were wrapped during migration
        if isinstance(value, dict) and len(value) == 1 and 'value' in value:
            return value['value']
        
        return value
    
    except Exception as e:
        print(f"⚠️  Error reading from cache (key={key}): {e}")
        return None


async def set_cache(key: str, value: Any) -> None:
    """Set a cached value for a key"""
    try:
        supabase = get_cache_client()
        cache_type, url_hash = _parse_cache_type(key)
        
        # Wrap simple values for JSONB storage
        if isinstance(value, (str, int, float, bool)):
            jsonb_value = {"value": value}
        elif isinstance(value, (dict, list)):
            jsonb_value = value
        elif value is None:
            jsonb_value = {"value": None}
        else:
            jsonb_value = {"value": str(value)}
        
        row = {
            "key": key,
            "value": jsonb_value,
            "cache_type": cache_type,
            "url_hash": url_hash if url_hash else None
        }
        
        # Use upsert to handle updates
        supabase.table('stagehand_cache').upsert(row, on_conflict='key').execute()
    
    except Exception as e:
        print(f"⚠️  Error writing to cache (key={key}): {e}")
        # Don't raise - cache failures shouldn't break the scraping


async def clear_cache_key(key: str) -> None:
    """Remove a specific key from cache"""
    try:
        supabase = get_cache_client()
        supabase.table('stagehand_cache').delete().eq('key', key).execute()
    
    except Exception as e:
        print(f"⚠️  Error clearing cache key (key={key}): {e}")
        # Don't raise - cache failures shouldn't break the scraping


# ---------- 2️⃣  DOM caching and change detection ---------------------------
async def get_dom_content(page) -> str:
    """Extract the main content area of the page for change detection"""
    try:
        # Get the main content area, focusing on article/blog content
        content_selectors = [
            'main', 'article', '.content', '.main-content', '.post-content',
            '.blog-content', '.entry-content', '[role="main"]', '.container'
        ]
        
        for selector in content_selectors:
            try:
                # Check if element exists first
                element = page.locator(selector).first
                if await element.count() > 0:
                    content = await element.inner_text()
                    if content and len(content.strip()) > 100:  # Ensure meaningful content
                        return content.strip()
            except Exception as e:
                print(f"⚠️  Error with selector '{selector}': {e}")
                continue
        
        # Fallback to body content if no specific content area found
        try:
            body = page.locator('body')
            return await body.inner_text()
        except Exception as e:
            print(f"⚠️  Error getting body content: {e}")
            return ""
        
    except Exception as e:
        print(f"⚠️  Error getting DOM content: {e}")
        return ""


async def check_dom_changes(page, url: str) -> Tuple[bool, str]:
    """Check if DOM content has changed since last cache"""
    url_key = url_hash(url)
    dom_hash_key = f"dom_hash_{url_key}"
    
    # Get current DOM content and hash
    current_content = await get_dom_content(page)
    current_hash = content_hash(current_content)
    
    # Get cached DOM hash
    cached_hash = await get_cache(dom_hash_key)
    
    if cached_hash is None:
        # First time, cache the hash
        print(f"🆕 First time accessing {url}, caching DOM hash")
        await set_cache(dom_hash_key, current_hash)
        return False, current_content
    
    if cached_hash == current_hash:
        # DOM hasn't changed
        print(f"🔄 DOM unchanged for {url}, using cached hash")
        return False, current_content
    else:
        # DOM has changed, update cache
        print(f"📢 DOM changed for {url}, updating DOM hash")
        await set_cache(dom_hash_key, current_hash)
        return True, current_content


# ---------- 3️⃣  Enhanced action caching -----------------------------------
async def observe_with_cache(page, cache_key: str, prompt: str, max_retries: int = 2) -> List[Any]:
    """Execute page.observe() with caching and retry logic"""
    for attempt in range(max_retries + 1):
        try:
            # Check cache first
            cached_actions = await get_cache(cache_key)
            if cached_actions and attempt == 0:  # Only use cache on first attempt
                print(f"🔄 Using cached actions for: {cache_key}")
                return cached_actions
            
            # Not in cache or retry, observe fresh
            print(f"🔍 Observing new actions for: {cache_key} (attempt {attempt + 1})")
            actions = await page.observe(prompt)
            
            # Ensure we have a list
            if not isinstance(actions, list):
                actions = [actions]
            
            # Cache the actions
            await set_cache(cache_key, actions)
            return actions
            
        except Exception as e:
            print(f"❌ Error observing actions (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                # Clear cache on retry attempts
                await clear_cache_key(cache_key)
                print("🔧 Clearing cache and retrying...")
            else:
                raise e


async def act_with_cache(page, cache_key: str, prompt: str, self_heal: bool = True) -> None:
    """Execute page actions with caching and self-healing"""
    try:
        # Get cached or fresh actions
        actions = await observe_with_cache(page, cache_key, prompt)
        
        # Execute all actions
        for i, action in enumerate(actions):
            print(f"🎯 Executing action {i + 1}/{len(actions)}")
            await page.act(action)
            
    except Exception as e:
        print(f"❌ Error executing cached actions: {e}")
        if self_heal:
            print("🔧 Self-healing: clearing cache and trying direct action...")
            await clear_cache_key(cache_key)
            # Fall back to direct action
            await page.act(prompt)
        else:
            raise e


# ---------- 4️⃣  Enhanced extraction with DOM caching ----------------------
# --- Update extract_link_with_cache to return (link, cache_hit) ---
async def extract_link_with_cache(page, list_page: str, max_retries: int = 2) -> Tuple[str, bool]:
    """Extract article link with DOM caching and validation retry. Returns (link, cache_hit)"""
    url_key = url_hash(list_page)
    cache_key = f"link_extraction_{url_key}"
    last_link_key = f"last_link_{url_key}"
    
    for attempt in range(max_retries + 1):
        try:
            # Navigate to page (always needed for DOM check)
            print(f"🔗 Navigating to {list_page} (attempt {attempt + 1})")
            await page.goto(list_page, timeout=45_000)
            
            # Check if DOM has changed
            dom_changed, dom_content = await check_dom_changes(page, list_page)
            
            # Check cache first (only if DOM hasn't changed and it's first attempt)
            if not dom_changed and attempt == 0:
                cached_result = await get_cache(cache_key)
                if cached_result:
                    print(f"🔄 Using cached link: {cached_result}")
                    return cached_result, True
            
            # DOM changed or not in cache or retry, extract fresh
            if dom_changed:
                print(f"📢 DOM changed, re-extracting link from {list_page}")
            else:
                print(f"🔍 Extracting link from {list_page} (attempt {attempt + 1})")
            
            link_result = await page.extract(
                instruction=("extract the link to the most recent blog post."),
                schema=LinkList,
            )
            
            extracted_link = str(link_result.link)
            
            # Cache the result
            await set_cache(cache_key, extracted_link)
            
            # Check if link has changed from last extraction
            last_link = await get_cache(last_link_key)
            if last_link and last_link != extracted_link:
                print(f"📢 Link changed from {last_link} to {extracted_link}")
                # Clear article cache for the old link
                old_article_key = f"article_extraction_{url_hash(last_link)}"
                await clear_cache_key(old_article_key)
                print("🧹 Cleared old article cache")
            
            # Update last known link
            await set_cache(last_link_key, extracted_link)
            
            print(f"✅ Extracted and cached link: {extracted_link}")
            return extracted_link, False
            
        except (ValidationError, ValueError) as e:
            print(f"❌ Link extraction validation failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                await clear_cache_key(cache_key)
                print("🔧 Clearing cache and retrying...")
            else:
                raise e
        except Exception as e:
            print(f"❌ Unexpected error in link extraction (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                await clear_cache_key(cache_key)
            else:
                raise e


# --- Update extract_article_with_cache to return (article, cache_hit) ---
async def extract_article_with_cache(page, url: str, max_retries: int = 2) -> tuple[Article, bool]:
    """Extract article with caching and validation retry. Returns (article, cache_hit)"""
    url_key = url_hash(url)
    cache_key = f"article_extraction_{url_key}"
    
    for attempt in range(max_retries + 1):
        try:
            # Navigate to page (always needed for DOM check)
            print(f"📰 Navigating to {url} (attempt {attempt + 1})")
            await page.goto(url, timeout=45_000)
            
            # Check if DOM has changed
            dom_changed, dom_content = await check_dom_changes(page, url)
            
            # Check cache first (only if DOM hasn't changed and it's first attempt)
            if not dom_changed and attempt == 0:
                cached_result = await get_cache(cache_key)
                if cached_result:
                    print(f"🔄 Using cached article: {cached_result.get('title', 'Unknown')}")
                    return Article(**cached_result), True
            
            # DOM changed or not in cache or retry, extract fresh
            if dom_changed:
                print(f"📢 DOM changed, re-extracting article from {url}")
            else:
                print(f"🔍 Extracting article from {url} (attempt {attempt + 1})")
            
            rec: Union[Article, dict] = await page.extract(
                instruction=(
                    "Extract the article title, author, ISO publication date "
                    "(YYYY-MM-DD) and every body paragraph as an array named content. "
                    "Ignore ads, nav, footer, sidebar."
                ),
                schema=Article,
            )
            
            article = rec if isinstance(rec, Article) else Article(**rec)
            
            # Validate article has meaningful content
            if not article.title or len(article.title.strip()) < 3:
                raise ValidationError("Article title is too short or missing")
            if not article.content or len(article.content) == 0:
                raise ValidationError("Article content is empty")
            
            # Cache the result - use mode='json' to serialize dates to strings
            await set_cache(cache_key, article.model_dump(mode='json'))
            print(f"✅ Extracted and cached article: {article.title}")
            
            return article, False
            
        except (ValidationError, ValueError) as e:
            print(f"❌ Article extraction validation failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                await clear_cache_key(cache_key)
                print("🔧 Clearing cache and retrying...")
            else:
                raise e
        except Exception as e:
            print(f"❌ Unexpected error in article extraction (attempt {attempt + 1}): {e}")
            if attempt < max_retries:
                await clear_cache_key(cache_key)
            else:
                raise e
