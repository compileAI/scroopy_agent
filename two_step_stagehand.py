import asyncio, os, sys, json, aiofiles, hashlib
from typing import Optional, Dict, Any, List
from datetime import date, datetime
from dotenv import load_dotenv; load_dotenv()

from pydantic import BaseModel, Field, field_validator, HttpUrl, ValidationError
import dateparser

from stagehand import Stagehand, StagehandConfig

# ---------- 1️⃣  small schemas ----------------------------------------------
class LinkList(BaseModel):
    link: HttpUrl = Field(..., min_length=1)   # enforce full URLs

class Article(BaseModel):
    title: str
    author: str
    date_published: date | None = None
    content: list[str]

    # lenient natural-language date → ISO date
    @field_validator("date_published", mode="before")
    @classmethod
    def parse_date(cls, v):
        if not v:
            return None
        parsed = dateparser.parse(v)
        if not parsed:
            raise ValueError("unparseable date")
        return parsed.date()

# ---------- 2️⃣  Stagehand client (local, Gemini) ---------------------------
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
if not API_KEY:
    sys.exit("❌  Put GEMINI_API_KEY in your .env")

CFG = StagehandConfig(
    env="LOCAL",
    model_name="gemini/gemini-2.0-flash"
)

# ---------- 3️⃣  Supabase Integration --------------------------------------
def get_supabase_client():
    """Get Supabase client with proper error handling"""
    try:
        from supabase import create_client, Client
    except ImportError:
        raise ImportError("Supabase client not installed. Install with: pip install supabase")
    
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables required")
    
    return create_client(supabase_url, supabase_key)

async def get_stagehand_sources() -> List[Dict[str, Any]]:
    """Get all sources from stagehand_sources table"""
    try:
        supabase = get_supabase_client()
        
        # Get all stagehand sources with their master_sources info
        response = supabase.table('stagehand_sources').select(
            '*, master_sources(name, url, scrape_method)'
        ).execute()
        
        if not response.data:
            print("📭 No stagehand sources found in database")
            return []
        
        print(f"📖 Found {len(response.data)} stagehand sources")
        return response.data
        
    except Exception as e:
        print(f"❌ Error fetching stagehand sources: {e}")
        return []

async def write_article_to_db(article: Article, source_id: int, url: str) -> bool:
    """Write extracted article to source_articles table"""
    try:
        supabase = get_supabase_client()
        
        # Prepare article data for database
        article_data = {
            'source_id': source_id,
            'url': url,
            'title': article.title,
            'author': article.author,
            'content': '\n\n'.join(article.content) if article.content else '',
            'published': article.date_published.isoformat() if article.date_published else None,
            'id': f"{source_id}_{hashlib.md5(url.encode()).hexdigest()[:16]}"  # Generate unique ID
        }
        
        # Check if article already exists
        existing = supabase.table('source_articles').select('id').eq('id', article_data['id']).execute()
        
        if existing.data:
            print(f"🔄 Article already exists in database: {article.title[:50]}...")
            return True
        
        # Insert new article
        result = supabase.table('source_articles').insert(article_data).execute()
        
        if result.data:
            print(f"✅ Successfully wrote article to database: {article.title[:50]}...")
            return True
        else:
            print(f"❌ Failed to write article to database: {article.title[:50]}...")
            return False
            
    except Exception as e:
        print(f"❌ Error writing article to database: {e}")
        return False

# ---------- 4️⃣  Enhanced cache utilities -----------------------------------
def url_hash(url: str) -> str:
    """Create a clean hash for URL-based cache keys"""
    return hashlib.md5(url.encode()).hexdigest()[:12]

def content_hash(content: str) -> str:
    """Create a hash of DOM content to detect changes"""
    return hashlib.md5(content.encode()).hexdigest()[:16]

async def get_cache(key: str) -> Optional[Any]:
    """Get cached value for a key, returns None if not found"""
    try:
        async with aiofiles.open("cache.json", 'r') as f:
            cache_content = await f.read()
            parsed = json.loads(cache_content)
            return parsed.get(key)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

async def set_cache(key: str, value: Any) -> None:
    """Set a cached value for a key"""
    try:
        async with aiofiles.open("cache.json", 'r') as f:
            cache_content = await f.read()
            parsed = json.loads(cache_content)
    except (FileNotFoundError, json.JSONDecodeError):
        parsed = {}
    
    parsed[key] = value
    
    async with aiofiles.open("cache.json", 'w') as f:
        await f.write(json.dumps(parsed, default=str, indent=2))

async def clear_cache_key(key: str) -> None:
    """Remove a specific key from cache"""
    try:
        async with aiofiles.open("cache.json", 'r') as f:
            cache_content = await f.read()
            parsed = json.loads(cache_content)
    except (FileNotFoundError, json.JSONDecodeError):
        return  # Nothing to clear
    
    if key in parsed:
        del parsed[key]
        async with aiofiles.open("cache.json", 'w') as f:
            await f.write(json.dumps(parsed, default=str, indent=2))

# ---------- 5️⃣  DOM caching and change detection ---------------------------
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
                element = await page.locator(selector).first
                if element:
                    content = await element.inner_text()
                    if content and len(content.strip()) > 100:  # Ensure meaningful content
                        return content.strip()
            except:
                continue
        
        # Fallback to body content if no specific content area found
        body = await page.locator('body')
        return await body.inner_text()
        
    except Exception as e:
        print(f"⚠️  Error getting DOM content: {e}")
        return ""

async def check_dom_changes(page, url: str) -> tuple[bool, str]:
    """Check if DOM content has changed since last cache"""
    url_key = url_hash(url)
    dom_cache_key = f"dom_content_{url_key}"
    dom_hash_key = f"dom_hash_{url_key}"
    
    # Get current DOM content
    current_content = await get_dom_content(page)
    current_hash = content_hash(current_content)
    
    # Get cached DOM hash
    cached_hash = await get_cache(dom_hash_key)
    
    if cached_hash is None:
        # First time, cache the content and hash
        print(f"🆕 First time accessing {url}, caching DOM content")
        await set_cache(dom_cache_key, current_content)
        await set_cache(dom_hash_key, current_hash)
        return False, current_content
    
    if cached_hash == current_hash:
        # DOM hasn't changed, use cached content
        print(f"🔄 DOM unchanged for {url}, using cached content")
        cached_content = await get_cache(dom_cache_key)
        return False, cached_content
    else:
        # DOM has changed, update cache
        print(f"📢 DOM changed for {url}, updating cache")
        await set_cache(dom_cache_key, current_content)
        await set_cache(dom_hash_key, current_hash)
        return True, current_content

# ---------- 6️⃣  Enhanced action caching -----------------------------------
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

# ---------- 7️⃣  Enhanced extraction with DOM caching ----------------------
# --- Update extract_link_with_cache to return (link, cache_hit) ---
async def extract_link_with_cache(page, list_page: str, max_retries: int = 2) -> tuple[str, bool]:
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
            
            rec: Article | dict = await page.extract(
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
            
            # Cache the result
            await set_cache(cache_key, article.model_dump())
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

# ---------- 8️⃣  Production main function ----------------------------------
async def process_single_source(sh: Stagehand, source: Dict[str, Any]) -> Dict[str, Any]:
    """Process a single source and return results"""
    source_id = source['id']
    source_name = source.get('master_sources', {}).get('name', 'Unknown')
    home_url = source['home_url']
    
    print(f"\n🚀 Processing source: {source_name} (ID: {source_id})")
    print(f"📍 Home URL: {home_url}")
    
    result = {
        'source_id': source_id,
        'source_name': source_name,
        'home_url': home_url,
        'status': 'failed',
        'error': None,
        'article': None,
        'article_url': None,
        'processing_time': 0
    }
    
    start_time = datetime.now()
    
    try:
        # Step 1: Get article link
        article_url, link_cache_hit = await extract_link_with_cache(sh.page, home_url)
        result['article_url'] = article_url
        
        # Step 2: Extract article
        article, article_cache_hit = await extract_article_with_cache(sh.page, article_url)
        result['article'] = article
        
        # Step 3: Only write to DB if both are cache misses
        if not link_cache_hit and not article_cache_hit:
            success = await write_article_to_db(article, source_id, article_url)
            if success:
                result['status'] = 'success'
                print(f"✅ Successfully processed {source_name}")
            else:
                result['status'] = 'failed'
                result['error'] = 'Failed to write to database'
                print(f"❌ Failed to write article to database for {source_name}")
        else:
            result['status'] = 'skipped'
            print(f"⏩ Skipped DB write for {source_name} (cache hit)")
        
    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)
        print(f"❌ Error processing {source_name}: {e}")
    
    finally:
        result['processing_time'] = (datetime.now() - start_time).total_seconds()
    
    return result

async def process_sources_batch(sources: List[Dict[str, Any]], batch_size: int = 5) -> List[Dict[str, Any]]:
    """Process sources in batches to avoid overwhelming the system"""
    all_results = []
    
    for i in range(0, len(sources), batch_size):
        batch = sources[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(sources) + batch_size - 1) // batch_size
        
        print(f"\n{'='*60}")
        print(f"📦 Processing batch {batch_num}/{total_batches} ({len(batch)} sources)")
        print(f"{'='*60}")
        
        batch_results = []
        
        # Process batch sequentially (can be parallelized later if needed)
        for j, source in enumerate(batch, 1):
            print(f"\n📊 Batch progress: {j}/{len(batch)}")
            
            # Initialize Stagehand for each source (to avoid session issues)
            sh = Stagehand(CFG)
            await sh.init()
            
            try:
                result = await process_single_source(sh, source)
                batch_results.append(result)
            finally:
                await sh.close()
            
        all_results.extend(batch_results)
    
    return all_results

async def main(batch_size: int = 5, max_sources: Optional[int] = None):
    """Production main function that processes all stagehand sources"""
    print("🏭 Starting production article extraction for all stagehand sources")
    
    # Get all sources from database
    sources = await get_stagehand_sources()
    
    if not sources:
        print("❌ No sources found. Exiting.")
        return
    
    # Limit sources if specified
    if max_sources:
        sources = sources[:max_sources]
        print(f"📊 Limited to {max_sources} sources")
    
    print(f"📊 Total sources to process: {len(sources)}")
    print(f"📦 Batch size: {batch_size}")
    
    start_time = datetime.now()
    
    try:
        # Process sources in batches
        results = await process_sources_batch(sources, batch_size)
        
        # Calculate statistics
        successful = sum(1 for r in results if r['status'] == 'success')
        skipped = sum(1 for r in results if r['status'] == 'skipped')
        failed = sum(1 for r in results if r['status'] == 'failed')
        written_to_db = successful  # Only successful ones were written to DB
        total_time = (datetime.now() - start_time).total_seconds()
        avg_time = sum(r['processing_time'] for r in results) / len(results) if results else 0
        
        # Print summary
        print(f"\n{'='*60}")
        print("📊 EXTRACTION SUMMARY")
        print(f"{'='*60}")
        print(f"Total sources processed: {len(sources)}")
        print(f"Successful extractions: {successful + skipped}")  # Including cache hits
        print(f"  └─ Written to database: {written_to_db}")      # Only fresh extractions
        print(f"  └─ Skipped (cache hits): {skipped}")
        print(f"Failed: {failed}")
        print(f"Success rate: {((successful + skipped)/len(sources)*100):.1f}%")
        print(f"Total processing time: {total_time:.1f}s")
        print(f"Average time per source: {avg_time:.1f}s")
        
        # Print failed sources
        if failed > 0:
            print(f"\n❌ Failed sources:")
            for result in results:
                if result['status'] == 'failed':
                    print(f"  - {result['source_name']}: {result['error']}")
        
        # Print successful extractions
        if successful > 0:
            print(f"\n✅ Fresh extractions (written to DB):")
            for result in results:
                if result['status'] == 'success':
                    article = result['article']
                    print(f"  - {result['source_name']}: {article.title[:60]}...")
        
        # Print skipped extractions
        if skipped > 0:
            print(f"\n⏩ Skipped extractions (cache hits):")
            for result in results:
                if result['status'] == 'skipped':
                    article = result['article']
                    print(f"  - {result['source_name']}: {article.title[:60]}...")
        
        print(f"\n💾 Summary Complete")
        
    except Exception as e:
        print(f"💥 Fatal error during processing: {e}")
        sys.exit(1)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Production article extraction for stagehand sources')
    parser.add_argument('--batch-size', type=int, default=5, help='Number of sources to process in each batch')
    parser.add_argument('--max-sources', type=int, help='Maximum number of sources to process (for testing)')
    
    args = parser.parse_args()
    
    asyncio.run(main(batch_size=args.batch_size, max_sources=args.max_sources))
