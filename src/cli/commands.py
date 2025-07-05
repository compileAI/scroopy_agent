"""
Command implementations for interactive CLI
"""

import json
import random
from typing import List
from urllib.parse import urlparse

# Import the tools
from tools.discovery import discover_sources
from tools.link_schema_generator import generate_link_schema
from tools.url_extractor import extract_urls_with_schema
from tools.article_scraper import generate_schema, extract_with_schema, patch_schema_with_feedback
from tools.supabase_writer import write_crawl_source

from .session import SimpleSession
from .display import (
    display_discovered_sources, display_extracted_urls, display_sample_urls,
    display_article_extraction, display_article_extraction_full, display_validation_results, display_schema_info,
    display_error, display_success, display_info, display_working_on,
    display_articles_list, display_schema_test_results
)


def get_help_text(session: SimpleSession) -> str:
    """Get context-aware help text"""
    if not session.has_current_url():
        return """
🤖 Scroopy Interactive CLI

Available commands:
  discover "<topic>"  - Find news sources for a topic
  use <url>          - Work directly with a URL (skip discovery)
  help               - Show this help
  exit               - Exit CLI

Examples: 
  discover "AI technology news"
  use https://techcrunch.com
"""
    
    elif not session.has_link_schema():
        return f"""
🤖 Working with: {session.current_source_name}

Available commands:
  link-schema        - Generate link extraction schema
  reset             - Clear current state and start over
  help              - Show this help
  exit              - Exit CLI
"""
    
    elif not session.has_sample_urls():
        return f"""
🤖 Working with: {session.current_source_name} (link schema ready)

Available commands:
  test-links        - Test link schema and show extracted URLs
  sample <count>    - Select sample URLs for article schema
  sample *          - Select all extracted URLs
  add-article <url> - Add specific URL to sample list
  debug-html        - Show HTML content of current URL
  grep-html <text>  - Search HTML content for text
  reset             - Clear current state and start over
  help              - Show this help
  exit              - Exit CLI

Examples: 
  sample 3
  sample *
  add-article https://example.com/article1
"""
    
    elif not session.has_article_schema():
        return f"""
🤖 Working with: {session.current_source_name} ({len(session.sample_urls)} samples ready)

Available commands:
  article-schema    - Generate article extraction schema
  list-articles     - Show all sample URLs
  add-article <url> - Add specific URL to sample list
  remove-article <id> - Remove URL from sample list
  clear-articles    - Clear all sample URLs
  debug-html        - Show HTML content of current URL
  grep-html <text>  - Search HTML content for text
  reset             - Clear current state and start over  
  help              - Show this help
  exit              - Exit CLI

Examples:
  article-schema
  add-article https://example.com/article2
  remove-article 1
"""
    
    else:
        return f"""
🤖 Working with: {session.current_source_name} (article schema ready)

Available commands:
  test-schema <id>  - Test schema on sample URL with full details (1-{len(session.sample_urls)})
  test-schema-all   - Test schema on all sample URLs
  test-article <id> - Test schema on sample URL (1-{len(session.sample_urls)})
  critique "<text>" - Apply manual feedback to improve schema
  critique "<text>" -s "<selectors>" - Apply feedback with custom selectors
  list-articles     - Show all sample URLs
  add-article <url> - Add specific URL to sample list
  remove-article <id> - Remove URL from sample list
  clear-articles    - Clear all sample URLs
  debug-html        - Show HTML content of current URL
  grep-html <text>  - Search HTML content for text
  inspect-schema    - Show current schema details
  save              - Save source to database
  reset             - Clear current state and start over
  help              - Show this help  
  exit              - Exit CLI

Examples: 
  test-schema 1
  test-schema 1 -e "content"
  test-schema-all
  critique "title selector needs to target h1.entry-title"
  critique "fix author field" -s "h1, h2, .author, .byline, .date"
  add-article https://example.com/article3
  grep-html "author"
  inspect-schema
"""


async def help_command(session: SimpleSession, args: List[str]):
    """Show context-aware help"""
    print(get_help_text(session))


async def discover_command(session: SimpleSession, args: List[str]):
    """Discover sources for a topic"""
    if not args:
        display_error("Usage: discover \"<topic>\"")
        return
        
    topic = " ".join(args)
    print(f"🔍 Discovering sources for: {topic}")
    
    try:
        # Call the discovery tool
        result_json = await discover_sources(topic)
        result = json.loads(result_json)
        
        if result["status"] == "success":
            session.discovered_sources = result["sources"]
            display_discovered_sources(result["sources"])
        else:
            display_error(f"Discovery failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        display_error(f"Discovery failed: {str(e)}")


async def use_command(session: SimpleSession, args: List[str]):
    """Use a source (either by ID from discovery or direct URL)"""
    if not args:
        display_error("Usage: use <id> or use <url>")
        return
    
    arg = args[0]
    
    # Check if it's a URL (contains http or looks like a domain)
    if arg.startswith(('http://', 'https://')) or '.' in arg:
        # Direct URL usage
        if not arg.startswith(('http://', 'https://')):
            arg = 'https://' + arg  # Add https if missing
        
        session.set_url_directly(arg)
        display_working_on(session.current_source_name, session.current_url)
        return
    
    # Otherwise treat as ID from discovery
    if not arg.isdigit():
        display_error("Usage: use <id> or use <url>")
        return
        
    if not session.discovered_sources:
        display_error("No sources discovered yet. Use 'discover' first or 'use <url>' for direct URL")
        return
        
    source_id = int(arg) - 1
    if source_id < 0 or source_id >= len(session.discovered_sources):
        display_error(f"Invalid ID. Use 1-{len(session.discovered_sources)}")
        return
        
    source = session.discovered_sources[source_id]
    session.current_url = source["url"]
    session.current_source_name = source["name"]
    
    display_working_on(session.current_source_name, session.current_url)


async def use_article_command(session: SimpleSession, args: List[str]):
    """Use a specific article URL for testing"""
    if not args:
        display_error("Usage: use-article <article_url>")
        return
    
    url = args[0]
    if not url.startswith(('http://', 'https://')):
        display_error("Please provide a full URL starting with http:// or https://")
        return
    
    session.set_url_directly(url)
    display_working_on(session.current_source_name, session.current_url)
    print("💡 Note: This is an article URL. You can test article extraction directly.")


async def link_schema_command(session: SimpleSession, args: List[str]):
    """Generate link extraction schema"""
    if not session.has_current_url():
        display_error("No URL set. Use 'discover' or 'use <url>' first")
        return
    
    print(f"🔗 Generating link schema for {session.current_source_name}...")
    
    try:
        result_json = await generate_link_schema(session.current_url)
        result = json.loads(result_json)
        
        if result["status"] == "success":
            session.link_schema = result["schema"]
            selector = session.link_schema.get('baseSelector', 'Unknown')
            display_success(f"Generated schema with selector: \"{selector}\"")
        else:
            display_error(f"Schema generation failed: {result.get('error', 'Unknown error')}")
            # For Substack, offer a known working schema
            if "substack.com" in session.current_url:
                print("💡 Would you like to use a known working Substack schema?")
                print("   Try: link-schema-manual")
            
    except Exception as e:
        display_error(f"Schema generation failed: {str(e)}")


async def link_schema_manual_command(session: SimpleSession, args: List[str]):
    """Manually set a link schema for common sites"""
    if not session.has_current_url():
        display_error("No URL set. Use 'discover' or 'use <url>' first")
        return
    
    # Check if it's a known site type
    if "substack.com" in session.current_url:
        # Use the working Substack schema
        session.link_schema = {
            'name': 'Substack Blog Article URLs',
            'baseSelector': "div[aria-label^='Post preview for'] a[data-testid='post-preview-title']",
            'fields': [
                {
                    'name': 'article_url',
                    'type': 'attribute',
                    'attribute': 'href'
                }
            ]
        }
        display_success("Set manual Substack link schema")
        print(f"   Selector: {session.link_schema['baseSelector']}")
    else:
        display_error("Manual schema not available for this site type")
        print("Supported sites: Substack")


async def debug_html_command(session: SimpleSession, args: List[str]):
    """Debug: Show what HTML is being returned"""
    if not session.has_current_url():
        display_error("No URL set. Use 'discover' or 'use <url>' first")
        return
    
    print(f"🔍 Debug: Fetching HTML from {session.current_url}")
    
    try:
        from utils.crawler_manager import get_shared_crawler
        
        crawler = await get_shared_crawler()
        result = await crawler.arun(url=session.current_url)
        
        if not result.success:
            display_error(f"Failed to fetch: {result.error}")
            return
        
        html_content = result.html
        print(f"✅ Fetched {len(html_content)} characters of HTML")
        
        # Show first 1000 characters
        print("\n📄 First 1000 characters:")
        print("-" * 50)
        print(html_content[:1000])
        print("-" * 50)
        
        # If we have a link schema, test the selector
        if session.has_link_schema():
            print(f"\n🔍 Testing selector: {session.link_schema['baseSelector']}")
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html_content, 'html.parser')
            elements = soup.select(session.link_schema['baseSelector'])
            
            print(f"   Found {len(elements)} elements")
            
            if elements:
                print("   First 3 elements:")
                for i, element in enumerate(elements[:3]):
                    href = element.get('href', 'No href')
                    text = element.get_text(strip=True)[:50]
                    print(f"     {i+1}. href='{href}' text='{text}...'")
            else:
                print("   No elements found with this selector")
                
                # Try some alternative selectors
                print("\n   🔍 Trying alternative selectors:")
                alt_selectors = [
                    "a[href*='/p/']",
                    "a[data-testid*='post']",
                    "div[aria-label*='Post'] a",
                    "a[href*='redwoodresearch.substack.com/p/']"
                ]
                
                for selector in alt_selectors:
                    elements = soup.select(selector)
                    if elements:
                        print(f"     ✅ '{selector}': {len(elements)} elements")
                        if len(elements) <= 3:
                            for elem in elements:
                                href = elem.get('href', 'No href')
                                print(f"       - {href}")
                    else:
                        print(f"     ❌ '{selector}': 0 elements")
        
    except Exception as e:
        display_error(f"Debug failed: {str(e)}")


async def grep_html_command(session: SimpleSession, args: List[str]):
    """Search HTML content for a string and return matching lines"""
    if not session.has_current_url():
        display_error("No URL set. Use 'discover' or 'use <url>' first")
        return
    
    if not args:
        display_error("Usage: grep-html <search_string>")
        return
    
    search_string = args[0]
    print(f"🔍 Searching HTML for: '{search_string}'")
    
    try:
        from utils.crawler_manager import get_shared_crawler
        
        crawler = await get_shared_crawler()
        result = await crawler.arun(url=session.current_url)
        
        if result.success:
            html_content = result.html
            lines = html_content.split('\n')
            matching_lines = []
            
            for i, line in enumerate(lines, 1):
                if search_string.lower() in line.lower():
                    # Truncate long lines for display
                    display_line = line.strip()
                    if len(display_line) > 120:
                        display_line = display_line[:117] + "..."
                    matching_lines.append((i, display_line))
            
            if matching_lines:
                print(f"✅ Found {len(matching_lines)} matching lines:")
                print("=" * 80)
                for line_num, line_content in matching_lines:
                    print(f"Line {line_num}: {line_content}")
                print("=" * 80)
            else:
                print(f"❌ No lines found containing '{search_string}'")
        else:
            display_error(f"Failed to fetch HTML: {result.error}")
            
    except Exception as e:
        display_error(f"HTML search failed: {str(e)}")


async def test_links_command(session: SimpleSession, args: List[str]):
    """Test the current link schema"""
    if not session.has_link_schema():
        display_error("No link schema available. Use 'link-schema' first")
        return
    
    print("🔍 Testing link schema...")
    
    try:
        # Convert schema to JSON string for the tool
        schema_json = json.dumps(session.link_schema)
        result_json = await extract_urls_with_schema(
            session.current_url, 
            schema_json, 
            max_urls=20
        )
        result = json.loads(result_json)
        
        if result["status"] == "success":
            session.extracted_urls = result["urls"]
            display_extracted_urls(session.extracted_urls)
        elif result["status"] == "warning":
            print(f"⚠️ {result.get('message', 'No URLs found')}")
            session.extracted_urls = result.get("urls", [])
            if session.extracted_urls:
                display_extracted_urls(session.extracted_urls)
        else:
            display_error(f"URL extraction failed: {result.get('error', 'Unknown error')}")
            
    except json.JSONDecodeError as e:
        display_error(f"Failed to parse URL extraction result: {str(e)}")
    except Exception as e:
        display_error(f"URL extraction failed: {str(e)}")


async def sample_command(session: SimpleSession, args: List[str]):
    """Select sample URLs for article schema generation"""
    if not session.extracted_urls:
        display_error("No extracted URLs available. Use 'test-links' first")
        return
    
    if not args:
        display_error("Usage: sample <count> or sample *")
        return
    
    if args[0] == "*":
        # Select all URLs
        session.sample_urls = session.extracted_urls.copy()
        display_success(f"Selected all {len(session.sample_urls)} URLs as samples")
    elif not args[0].isdigit():
        display_error("Usage: sample <count> or sample *")
        return
    else:
        count = int(args[0])
        if count <= 0:
            display_error("Sample count must be positive")
            return
        
        available_count = len(session.extracted_urls)
        if count > available_count:
            display_error(f"Only {available_count} URLs available. Use a smaller number or * for all")
            return
        
        # Randomly select sample URLs
        session.sample_urls = random.sample(session.extracted_urls, count)
        display_success(f"Selected {count} URLs as samples for article schema generation")
    
    display_sample_urls(session.sample_urls)


async def article_schema_command(session: SimpleSession, args: List[str]):
    """Generate article extraction schema (schema generation only, no validation)"""
    if not session.has_sample_urls():
        display_error("No sample URLs available. Use 'sample <count>' or 'add-article <url>' first")
        return
    
    print(f"🎯 Generating article schema using first sample URL...")
    print("⏱️  This may take a moment...")
    
    try:
        # Get HTML content from first sample URL
        from utils.crawler_manager import get_shared_crawler
        
        test_url = session.sample_urls[0]
        crawler = await get_shared_crawler()
        result = await crawler.arun(url=test_url)
        
        if not result.success:
            display_error(f"Failed to fetch HTML from {test_url}")
            return
        
        html_content = result.html
        if not html_content or len(html_content) < 100:
            display_error(f"No substantial content found in {test_url}")
            return
        
        # Generate schema using the new simplified function
        schema = await generate_schema(html_content)
        
        if schema:
            session.article_schema = schema
            session.validation_score = None  # No validation score since we didn't validate
            
            display_success("Generated article schema (schema generation only)")
            display_schema_info(schema, "article schema")
        else:
            display_error("Article schema generation failed")
            
    except Exception as e:
        display_error(f"Article schema generation failed: {str(e)}")


async def test_article_command(session: SimpleSession, args: List[str]):
    """Test article schema on a specific sample URL"""
    if not session.has_article_schema():
        display_error("No article schema available. Use 'article-schema' first")
        return
    
    if not args or not args[0].isdigit():
        display_error(f"Usage: test-article <id> (1-{len(session.sample_urls)})")
        return
    
    url_id = int(args[0]) - 1
    if url_id < 0 or url_id >= len(session.sample_urls):
        display_error(f"Invalid ID. Use 1-{len(session.sample_urls)}")
        return
    
    url = session.sample_urls[url_id]
    
    try:
        # Use the new simplified extraction function
        extraction = await extract_with_schema(url, session.article_schema)
        display_article_extraction(extraction, url)
        
    except Exception as e:
        display_error(f"Article extraction failed: {str(e)}")

async def save_command(session: SimpleSession, args: List[str]):
    """Save the current source to database"""
    if not session.has_article_schema():
        display_error("No article schema available. Complete the workflow first")
        return
    

    
    print("💾 Saving source to database...")
    
    try:
        # Prepare source data for database
        source_data = {
            "source": {
                "name": session.current_source_name,
                "url": session.current_url,
                "description": f"Source added via interactive CLI"
            },
            "link_schema": session.link_schema,
            "article_schema": session.article_schema,
            "sample_urls": session.sample_urls
        }
        
        result_json = await write_crawl_source(source_data)
        result = json.loads(result_json)
        
        if result["status"] == "success":
            display_success("Successfully saved source to database")
        elif result["status"] == "skipped":
            display_info(f"Source already exists with better/equal score: {result.get('message', '')}")
        else:
            display_error(f"Save failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        display_error(f"Save failed: {str(e)}")


async def reset_command(session: SimpleSession, args: List[str]):
    """Reset all session state"""
    session.reset()
    display_success("Cleared session state")


async def exit_command(session: SimpleSession, args: List[str]):
    """Exit the CLI"""
    print("👋 Goodbye!")
    # Small delay to ensure message is printed
    import asyncio
    await asyncio.sleep(0.1)
    return True  # Signal to exit


# New CRUD commands for managing sample URLs
async def list_articles_command(session: SimpleSession, args: List[str]):
    """List all sample URLs"""
    display_articles_list(session.sample_urls)


async def add_article_command(session: SimpleSession, args: List[str]):
    """Add a URL to the sample list"""
    if not args:
        display_error("Usage: add-article <url>")
        return
    
    url = args[0]
    if not url.startswith(('http://', 'https://')):
        display_error("Please provide a full URL starting with http:// or https://")
        return
    
    if session.add_sample_url(url):
        display_success(f"Added article: {url}")
    else:
        display_info(f"Article already in list: {url}")


async def remove_article_command(session: SimpleSession, args: List[str]):
    """Remove a URL from the sample list by ID"""
    if not args or not args[0].isdigit():
        display_error(f"Usage: remove-article <id> (1-{len(session.sample_urls)})")
        return
    
    url_id = int(args[0])
    if session.remove_sample_url(url_id):
        display_success(f"Removed article ID {url_id}")
    else:
        display_error(f"Invalid ID. Use 1-{len(session.sample_urls)}")


async def clear_articles_command(session: SimpleSession, args: List[str]):
    """Clear all sample URLs"""
    count = len(session.sample_urls)
    session.clear_sample_urls()
    display_success(f"Cleared {count} sample URLs")


# New schema testing commands
async def test_schema_command(session: SimpleSession, args: List[str]):
    """Test the current schema on a specific sample URL with full details"""
    if not session.has_article_schema():
        display_error("No article schema available. Use 'article-schema' first")
        return
    
    if not args or not args[0].isdigit():
        display_error(f"Usage: test-schema <id> [-e \"field_name\"] (1-{len(session.sample_urls)})")
        return
    
    url_id = int(args[0])
    url = session.get_sample_url(url_id)
    
    if not url:
        display_error(f"Invalid ID. Use 1-{len(session.sample_urls)}")
        return
    
    # Parse exclude option
    exclude_field = None
    if len(args) >= 3 and args[1] == "-e":
        exclude_field = args[2]
    
    try:
        # Use the new simplified extraction function
        extraction = await extract_with_schema(url, session.article_schema)
        display_article_extraction_full(extraction, url, exclude_field)
        
    except Exception as e:
        display_error(f"Schema testing failed: {str(e)}")


async def test_schema_all_command(session: SimpleSession, args: List[str]):
    """Test the current schema on all sample URLs"""
    if not session.has_article_schema():
        display_error("No article schema available. Use 'article-schema' first")
        return
    
    if not session.has_sample_urls():
        display_error("No sample URLs available")
        return
    
    print(f"🧪 Testing schema on all {len(session.sample_urls)} sample URLs...")
    
    try:
        # Use the new simplified extraction function
        results = []
        for url in session.sample_urls:
            try:
                extraction = await extract_with_schema(url, session.article_schema)
                results.append(extraction)
            except Exception as e:
                print(f"❌ Failed to test {url}: {e}")
                results.append(None)
        
        display_schema_test_results(results, session.sample_urls)
        
    except Exception as e:
        display_error(f"Schema testing failed: {str(e)}")


# Manual critique command
async def critique_command(session: SimpleSession, args: List[str]):
    """Apply manual feedback to improve the article schema using diffing approach"""
    if not session.has_article_schema():
        display_error("No article schema available. Use 'article-schema' first")
        return
    
    if not session.has_sample_urls():
        display_error("No sample URLs available. Add some URLs first")
        return
    
    if not args:
        display_error("Usage: critique \"<feedback text>\" [-s \"<selectors>\"]")
        return
    
    # Parse arguments for feedback and optional selectors
    feedback = ""
    candidate_selectors = "h1, h2, h3, .title, .headline, .author, .byline, .date, .published, time, .content, .article-body, p"
    
    i = 0
    while i < len(args):
        if args[i] == "-s" and i + 1 < len(args):
            candidate_selectors = args[i + 1]
            i += 2
        else:
            feedback += args[i] + " "
            i += 1
    
    feedback = feedback.strip()
    if not feedback:
        display_error("Usage: critique \"<feedback text>\" [-s \"<selectors>\"]")
        return
    
    session.validation_feedback.append(feedback)
    
    print(f"🔄 Applying manual feedback to improve article schema...")
    print(f"   Feedback: {feedback}")
    print(f"   Selectors: {candidate_selectors}")
    
    try:
        # Get HTML content from first sample URL for context
        from utils.crawler_manager import get_shared_crawler
        
        test_url = session.sample_urls[0]
        crawler = await get_shared_crawler()
        result = await crawler.arun(url=test_url)
        
        if not result.success:
            display_error(f"Failed to fetch HTML from {test_url}")
            return
        
        html_content = result.html
        
        # Use the new diffing approach
        improved_schema = await patch_schema_with_feedback(
            html=html_content,
            old_schema=session.article_schema,
            feedback=feedback,
            candidate_selectors=candidate_selectors
        )
        
        if improved_schema:
            session.article_schema = improved_schema
            
            display_success("Generated improved schema with manual feedback")
            display_schema_info(session.article_schema, "improved article schema")
        else:
            display_error("Schema improvement failed")
            
    except Exception as e:
        display_error(f"Schema improvement failed: {str(e)}")


async def inspect_schema_command(session: SimpleSession, args: List[str]):
    """Inspect the current article schema in detail"""
    if not session.has_article_schema():
        display_error("No article schema available. Use 'article-schema' first")
        return
    
    schema = session.article_schema
    print("🔍 Current Article Schema:")
    print("=" * 80)
    
    # Display schema details
    print(f"📋 Name: {schema.get('name', 'Unknown')}")
    print(f"🎯 Base Selector: {schema.get('baseSelector', 'N/A')}")
    print(f"📄 Source URL: {schema.get('source_url', 'N/A')}")
    print(f"🔗 Generated from: {schema.get('generated_from', 'N/A')}")
    print(f"🔄 Attempt: {schema.get('attempt', 'N/A')}")
    
    fields = schema.get('fields', [])
    print(f"\n📝 Fields ({len(fields)}):")
    print("-" * 40)
    
    for i, field in enumerate(fields, 1):
        field_name = field.get('name', 'unnamed')
        field_type = field.get('type', 'unknown')
        selector = field.get('selector', 'N/A')
        
        print(f"{i}. {field_name} ({field_type})")
        print(f"   Selector: {selector}")
        
        # Show nested fields if any
        nested_fields = field.get('fields', [])
        if nested_fields:
            print(f"   Nested fields:")
            for nested_field in nested_fields:
                nested_name = nested_field.get('name', 'unnamed')
                nested_type = nested_field.get('type', 'unknown')
                print(f"     - {nested_name} ({nested_type})")
        print()
    
    print("=" * 80)


# Command registry
COMMANDS = {
    "help": help_command,
    "discover": discover_command,
    "use": use_command,
    "use-article": use_article_command,
    "link-schema": link_schema_command,
    "link-schema-manual": link_schema_manual_command,
    "debug-html": debug_html_command,
    "grep-html": grep_html_command,
    "test-links": test_links_command,
    "sample": sample_command,
    "article-schema": article_schema_command,
    "test-article": test_article_command,
    "save": save_command,
    "reset": reset_command,
    "exit": exit_command,
    # New CRUD commands
    "list-articles": list_articles_command,
    "add-article": add_article_command,
    "remove-article": remove_article_command,
    "clear-articles": clear_articles_command,
    # New schema testing commands
    "test-schema": test_schema_command,
    "test-schema-all": test_schema_all_command,
    # Manual critique command
    "critique": critique_command,
    # Debug commands
    "inspect-schema": inspect_schema_command,
} 