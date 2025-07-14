from supabase import create_client, Client
from typing import Optional, Dict, Any, List
import os
from models import Article

def get_supabase_client() -> Client:
    """Get Supabase client with proper error handling"""

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

def add_source_to_database(source_url: str, source_name: str) -> bool:
    """
    Add a new source to the database.
    
    Args:
        source_url: The URL of the source
        source_name: The name of the source
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        supabase = get_supabase_client()
        
        # First, insert into master_sources table
        master_source_data = {
            "url": source_url,
            "name": source_name,
            "scrape_method": "stagehand",
            "active": True
        }
        
        master_result = supabase.table("master_sources").insert(master_source_data).execute()
        
        if not master_result.data:
            print("Error: Failed to insert into master_sources table")
            return False
        
        # Get the auto-assigned ID from the inserted record
        master_source_id = master_result.data[0]["id"]
        
        # Insert into stagehand_sources table
        stagehand_source_data = {
            "id": master_source_id,
            "name": source_name,
            "home_url": source_url
        }
        
        stagehand_result = supabase.table("stagehand_sources").insert(stagehand_source_data).execute()
        
        if not stagehand_result.data:
            print("Error: Failed to insert into stagehand_sources table")
            # TODO: Consider rolling back the master_sources insert
            return False
        
        print(f"Successfully added source '{source_name}' to database with ID: {master_source_id}")
        return True
        
    except Exception as e:
        print(f"Database error: {str(e)}")
        return False

def check_source_exists(source_url: str) -> bool:
    """
    Check if a source URL already exists in the database.
    
    Args:
        source_url: The URL to check
        
    Returns:
        bool: True if source exists, False otherwise
    """
    try:
        supabase = get_supabase_client()
        
        result = supabase.table("master_sources").select("id").eq("url", source_url).execute()
        
        return len(result.data) > 0
        
    except Exception as e:
        print(f"Error checking source existence: {str(e)}")
        return False

def check_source_name_exists(source_name: str) -> bool:
    """
    Check if a source name already exists in the database.
    
    Args:
        source_name: The name to check
        
    Returns:
        bool: True if name exists, False otherwise
    """
    try:
        supabase = get_supabase_client()
        
        result = supabase.table("master_sources").select("id").eq("name", source_name).execute()
        
        return len(result.data) > 0
        
    except Exception as e:
        print(f"Error checking source name existence: {str(e)}")
        return False
