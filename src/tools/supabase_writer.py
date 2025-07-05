"""
Supabase CrawlSource writer tool for Scroopy agent

Writes validated crawl sources to Supabase database.
"""

import json
import logging
import os
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

async def write_crawl_source(source_data: Dict[str, Any]) -> str:
    """
    Write a CrawlSource to Supabase database.
    
    Writes sources that have both link and article schemas.
    
    Args:
        source_data: Dictionary containing:
            - source: Basic source info (name, url, description)
            - link_schema: Link extraction schema  
            - article_schema: Article extraction schema
            - sample_urls: List of sample URLs used for testing
            
    Returns:
        JSON string with write operation results
    """
    logger.info(f"💾 Writing CrawlSource to Supabase")
    
    try:
        # Validate input data structure
        required_fields = ['source', 'link_schema', 'article_schema']
        missing_fields = [field for field in required_fields if field not in source_data]
        
        if missing_fields:
            return json.dumps({
                "status": "error",
                "error": f"Missing required fields: {missing_fields}",
                "required_fields": required_fields
            })
        
        # Check that both schemas are present and valid
        link_schema = source_data.get('link_schema')
        article_schema = source_data.get('article_schema')
        
        if not link_schema or not article_schema:
            return json.dumps({
                "status": "error", 
                "error": "Both link_schema and article_schema must be present and non-null",
                "has_link_schema": bool(link_schema),
                "has_article_schema": bool(article_schema)
            })
        
        # Import Supabase client
        try:
            from supabase import create_client, Client
        except ImportError:
            return json.dumps({
                "status": "error",
                "error": "Supabase client not installed. Install with: pip install supabase"
            })
        
        # Get Supabase credentials from environment (using SERVICE_ROLE_KEY for write operations)
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        
        if not supabase_url or not supabase_key:
            return json.dumps({
                "status": "error",
                "error": "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables required",
                "has_url": bool(supabase_url),
                "has_key": bool(supabase_key)
            })
        
        # Initialize Supabase client
        supabase: Client = create_client(supabase_url, supabase_key)
        
        # Extract source information
        source_info = source_data['source']
        source_name = source_info.get('name', 'Unknown')
        source_url = source_info.get('url')
        
        # Handle article_schema wrapper structure
        if isinstance(article_schema, dict) and 'schema' in article_schema and 'status' in article_schema:
            # Extract actual schema from wrapper
            article_schema = article_schema.get('schema', {})
        
        print(f"   💾 Writing CrawlSource: {source_name} ({source_url})")
        print(f"   🔗 Link Schema Fields: {len(link_schema.get('fields', []))}")
        print(f"   📰 Article Schema Fields: {len(article_schema.get('fields', []))}")
        
        # Check if source already exists in master_sources (by URL)
        existing_check = supabase.table('master_sources').select('id,name,scrape_method').eq('url', source_url).execute()
        
        if existing_check.data and len(existing_check.data) > 0:
            existing_source = existing_check.data[0]
            existing_id = existing_source['id']
            existing_name = existing_source.get('name')
            scrape_method = existing_source.get('scrape_method')
            
            print(f"   ⚠️ Source already exists in master_sources: {existing_name} (ID: {existing_id}, method: {scrape_method})")
            
            # Check if this source exists in crawl_sources
            crawl_check = supabase.table('crawl_sources').select('source_id,name').eq('source_id', existing_id).execute()
            
            if crawl_check.data and len(crawl_check.data) > 0:
                # Source exists in crawl_sources - update it
                print(f"   🔄 Updating existing crawl source")
                
                # Update existing record in crawl_sources
                update_result = supabase.table('crawl_sources').update({
                    'name': source_name,
                    'link_schema': link_schema,
                    'article_schema': article_schema,
                    'home_url': source_url
                }).eq('source_id', existing_id).execute()
                
                if update_result.data:
                    print(f"   ✅ Successfully updated CrawlSource (source_id: {existing_id})")
                    return json.dumps({
                        "status": "success",
                        "operation": "update",
                        "source_id": existing_id,
                        "source_name": source_name,
                        "source_url": source_url,
                        "message": f"Updated existing source"
                    })
                else:
                    return json.dumps({
                        "status": "error",
                        "error": "Failed to update existing record in crawl_sources",
                        "source_id": existing_id
                    })
            else:
                # Source exists in master_sources but not in crawl_sources - add to crawl_sources
                print(f"   ➕ Adding existing master source to crawl_sources")
                
                crawl_insert_result = supabase.table('crawl_sources').insert({
                    'source_id': existing_id,
                    'name': source_name,
                    'link_schema': link_schema,
                    'article_schema': article_schema,
                    'home_url': source_url
                }).execute()
                
                if crawl_insert_result.data:
                    print(f"   ✅ Successfully added to crawl_sources (source_id: {existing_id})")
                    return json.dumps({
                        "status": "success",
                        "operation": "insert_crawl_only",
                        "source_id": existing_id,
                        "source_name": source_name,
                        "source_url": source_url,
                        "message": f"Added existing master source to crawl_sources"
                    })
                else:
                    return json.dumps({
                        "status": "error",
                        "error": "Failed to insert into crawl_sources",
                        "source_id": existing_id
                    })
        else:
            # Source doesn't exist - insert into both master_sources and crawl_sources
            print(f"   ➕ Inserting new source into master_sources and crawl_sources")
            
            # Insert into master_sources first
            master_response = supabase.table("master_sources").insert({
                "name": source_name,
                "url": source_url,
                "scrape_method": "crawl"
            }).execute()

            if not master_response.data or len(master_response.data) == 0:
                return json.dumps({
                    "status": "error",
                    "error": "Failed to insert into master_sources"
                })

            master_source = master_response.data[0]
            source_id = master_source["id"]
            print(f"   ✅ Inserted into master_sources with id {source_id}")

            # Insert into crawl_sources
            crawl_response = supabase.table("crawl_sources").insert({
                "source_id": source_id,
                "link_schema": link_schema,
                "article_schema": article_schema,
                "home_url": source_url,
                "name": source_name
            }).execute()

            if crawl_response.data and len(crawl_response.data) > 0:
                print(f"   ✅ Successfully inserted CrawlSource (source_id: {source_id})")
                
                return json.dumps({
                    "status": "success",
                    "operation": "insert",
                    "source_id": source_id,
                    "source_name": source_name,
                    "source_url": source_url,
                    "message": f"Successfully added new CrawlSource"
                })
            else:
                # Cleanup master_sources entry if crawl_sources insert failed
                try:
                    supabase.table("master_sources").delete().eq("id", source_id).execute()
                    print(f"   🧹 Cleaned up master_sources entry (ID: {source_id})")
                except Exception:
                    pass
                    
                return json.dumps({
                    "status": "error",
                    "error": "Failed to insert into crawl_sources",
                    "source_id": source_id
                })
        
    except Exception as e:
        error_msg = f"Error writing to Supabase: {str(e)}"
        logger.error(f"❌ {error_msg}")
        print(f"❌ TOOL ERROR: {error_msg}")
        return json.dumps({
            "status": "error", 
            "error": error_msg,
            "exception_type": type(e).__name__
        })


async def get_crawl_sources(limit: int = 50, status: str = "active") -> str:
    """
    Retrieve CrawlSources from Supabase database.
    
    Args:
        limit: Maximum number of records to return
        status: Filter by status ('active', 'inactive', 'all')
        
    Returns:
        JSON string with retrieved sources
    """
    logger.info(f"📖 Retrieving CrawlSources from Supabase (limit: {limit}, status: {status})")
    
    try:
        # Import Supabase client
        try:
            from supabase import create_client, Client
        except ImportError:
            return json.dumps({
                "status": "error",
                "error": "Supabase client not installed. Install with: pip install supabase"
            })
        
        # Get Supabase credentials (using SERVICE_ROLE_KEY for read operations)
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        
        if not supabase_url or not supabase_key:
            return json.dumps({
                "status": "error",
                "error": "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables required"
            })
        
        # Initialize Supabase client
        supabase: Client = create_client(supabase_url, supabase_key)
        
        # Build query - join with master_sources to get complete info
        query = supabase.table('crawl_sources').select('*,master_sources(name,url,scrape_method,created_at)')
        
        # Note: crawl_sources table doesn't have a 'status' field in the current schema
        # so we'll skip status filtering for now
        
        query = query.limit(limit)
        
        # Execute query
        result = query.execute()
        
        if result.data:
            print(f"   ✅ Retrieved {len(result.data)} CrawlSources")
            return json.dumps({
                "status": "success",
                "sources": result.data,
                "count": len(result.data),
                "limit": limit,
                "filter_status": status
            })
        else:
            return json.dumps({
                "status": "success",
                "sources": [],
                "count": 0,
                "message": "No sources found matching criteria"
            })
            
    except Exception as e:
        error_msg = f"Error retrieving from Supabase: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return json.dumps({
            "status": "error",
            "error": error_msg
        }) 