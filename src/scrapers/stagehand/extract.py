import asyncio
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

from stagehand import Stagehand

# Import from new utils structure
import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from models.source_article import SourceArticle
from models.stagehand import Article
from utils.stagehand_cache import extract_link_with_cache, extract_article_with_cache
from utils.supabase import write_article_to_db
from utils.ids import generate_deterministic_id
from .client import get_initialized_client


async def process_single_source(
    sh: Stagehand, 
    source: Union[Dict[str, Any], str], 
    write_to_db: bool = True
) -> Dict[str, Any]:
    """Process a single source and return results."""
    
    # Handle both database source dict and single URL string
    if isinstance(source, str):
        source_id = -1  # Dummy ID for testing
        source_name = 'Test URL'
        home_url = source
    else:
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
        
        # Step 3: Write to DB only if requested and both are cache misses
        if write_to_db and not link_cache_hit and not article_cache_hit:
            success = await write_article_to_db(article, source_id, article_url)
            if success:
                result['status'] = 'success'
                print(f"✅ Successfully processed {source_name}")
            else:
                result['status'] = 'failed'
                result['error'] = 'Failed to write to database'
                print(f"❌ Failed to write article to database for {source_name}")
        elif write_to_db and (link_cache_hit or article_cache_hit):
            result['status'] = 'skipped'
            print(f"⏩ Skipped DB write for {source_name} (cache hit)")
        else:
            result['status'] = 'success'
            print(f"✅ Successfully extracted {source_name} (no DB write)")
        
    except Exception as e:
        result['status'] = 'failed'
        result['error'] = str(e)
        print(f"❌ Error processing {source_name}: {e}")
    
    finally:
        result['processing_time'] = (datetime.now() - start_time).total_seconds()
    
    return result


def convert_article_to_source_article(
    article: Article, 
    source_id: int, 
    url: str
) -> SourceArticle:
    """Convert a Stagehand Article to SourceArticle format."""
    # Generate deterministic ID
    article_id = generate_deterministic_id("stagehand", str(source_id), url)
    
    source_article = SourceArticle(
        published=article.date_published.isoformat() if article.date_published else None,
        title=article.title,
        content='\n\n'.join(article.content) if article.content else '',
        author=article.author,
        source_id=source_id,
        url=url
    )
    # Override the auto-generated ID with the deterministic one
    source_article.id = article_id
    return source_article


async def process_sources_batch(
    sources: List[Dict[str, Any]], 
    batch_size: int = 5,
    convert_to_source_articles: bool = False
) -> List[Union[Dict[str, Any], SourceArticle]]:
    """Process sources in batches to avoid overwhelming the system."""
    all_results = []
    
    for i in range(0, len(sources), batch_size):
        batch = sources[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(sources) + batch_size - 1) // batch_size
        
        print(f"\n{'='*60}")
        print(f"📦 Processing batch {batch_num}/{total_batches} ({len(batch)} sources)")
        print(f"{'='*60}")
        
        batch_results = []
        
        # Process batch sequentially
        for j, source in enumerate(batch, 1):
            print(f"\n📊 Batch progress: {j}/{len(batch)}")
            
            # Initialize Stagehand for each source (to avoid session issues)
            sh = await get_initialized_client()
            
            try:
                result = await process_single_source(sh, source)
                
                if convert_to_source_articles and result['status'] in ['success', 'skipped'] and result['article']:
                    # Convert to SourceArticle format
                    source_article = convert_article_to_source_article(
                        result['article'], 
                        result['source_id'], 
                        result['article_url']
                    )
                    batch_results.append(source_article)
                else:
                    batch_results.append(result)
                    
            finally:
                await sh.close()
            
        all_results.extend(batch_results)
    
    return all_results