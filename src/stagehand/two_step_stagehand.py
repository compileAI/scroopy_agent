import asyncio, os, sys
from typing import Optional, Dict, Any, List
from datetime import date, datetime
from dotenv import load_dotenv; load_dotenv()

from stagehand import Stagehand, StagehandConfig

# Import our utility functions
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
from supabase_utils import add_source_to_database, check_source_exists, check_source_name_exists, get_stagehand_sources, write_article_to_db
from general_utils import prompt_for_source_addition, get_user_input
from cache_utils import extract_link_with_cache, extract_article_with_cache

# ---------- 1️⃣  Stagehand client (local, Gemini) ---------------------------
API_KEY = os.getenv("GEMINI_API_KEY") # For some reason, Stagehand doesn't like GOOGLE_API_KEY...
if not API_KEY:
    sys.exit("❌  Put GEMINI_API_KEY in your .env")

CFG = StagehandConfig(
    env="LOCAL",
    model_name="gemini/gemini-2.0-flash"
)

# ---------- 2️⃣  Production main function ----------------------------------
async def process_single_source(sh: Stagehand, source: Dict[str, Any] | str, write_to_db: bool = True) -> Dict[str, Any]:
    """Process a single source and return results"""
    
    # Handle both database source dict and single URL string
    if isinstance(source, str):
        # Single URL mode
        source_id = -1  # Dummy ID
        source_name = 'Test URL'
        home_url = source
    else:
        # Database source mode
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
            # Single URL mode or cache hit without DB write
            result['status'] = 'success'
            print(f"✅ Successfully extracted {source_name} (no DB write)")
        
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

async def main(batch_size: int = 5, max_sources: Optional[int] = None, single_url: Optional[str] = None):
    """Production main function that processes all stagehand sources or a single URL"""
    
    if single_url:
        # Single URL mode
        print(f"🔍 Running two-step extraction on single URL: {single_url}")
        
        # Check if source already exists in database
        if check_source_exists(single_url):
            print(f"⚠️  Source URL already exists in database: {single_url}")
            answer = get_user_input("Do you still want to extract this source? (y/n)")
            if answer == "y":
                print("Continuing with extraction for testing purposes...")
            else:
                print("Exiting...")
                return
        
        # Initialize Stagehand
        sh = Stagehand(CFG)
        await sh.init()
        
        try:
            result = await process_single_source(sh, single_url, write_to_db=False)
            
            # Print results for single URL
            print(f"\n{'='*60}")
            print("📊 SINGLE URL EXTRACTION RESULTS")
            print(f"{'='*60}")
            
            if result['status'] == 'success':
                article = result['article']
                print(f"✅ SUCCESS: Article extracted successfully")
                print(f"📰 Title: {article.title}")
                print(f"✍️  Author: {article.author}")
                print(f"📅 Published: {article.date_published}")
                print(f"🔗 URL: {result['article_url']}")
                print(f"📝 Content: {article.content}")
                
                # Interactive source addition workflow
                source_name = prompt_for_source_addition(single_url)
                
                if source_name:
                    # Check if source name already exists
                    if check_source_name_exists(source_name):
                        print(f"❌ Error: Source name '{source_name}' already exists in database")
                        print("Please choose a different name and try again.")
                    else:
                        # Add source to database
                        success = add_source_to_database(single_url, source_name)
                        if success:
                            print(f"✅ Source '{source_name}' successfully added to database!")
                        else:
                            print(f"❌ Failed to add source '{source_name}' to database")
                
            elif result['status'] == 'skipped':
                article = result['article']
                print(f"⏩ SKIPPED: Article was cached (not written to database)")
                print(f"📰 Title: {article.title}")
                print(f"✍️  Author: {article.author}")
                print(f"📅 Published: {article.date_published}")
                print(f"🔗 URL: {result['article_url']}")
            else:
                print(f"❌ FAILED: {result['error']}")
                
        finally:
            await sh.close()
        return
    
    # Production mode - process all sources from database
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
    parser.add_argument('--url', type=str, help='Single URL to test extraction on (instead of processing all sources)')
    
    args = parser.parse_args()
    
    asyncio.run(main(batch_size=args.batch_size, max_sources=args.max_sources, single_url=args.url))
