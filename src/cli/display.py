"""
Display utilities for interactive CLI
"""

from typing import List, Dict, Any
from urllib.parse import urlparse


def display_discovered_sources(sources: List[Dict[str, Any]]):
    """Display discovered sources in a nice format"""
    print(f"📋 Found {len(sources)} sources:")
    for i, source in enumerate(sources, 1):
        print(f"  [{i}] {source['name']} ({source['url']})")
    print("\nUse 'use <id>' to select a source")


def display_extracted_urls(urls: List[str], max_display: int = 15):
    """Display extracted URLs"""
    print(f"🔍 Found {len(urls)} article URLs:")
    
    display_count = min(len(urls), max_display)
    for i in range(display_count):
        url = urls[i]
        # Truncate long URLs for display
        display_url = url if len(url) <= 80 else url[:77] + "..."
        print(f"  [{i+1}] {display_url}")
    
    if len(urls) > max_display:
        print(f"  ... and {len(urls) - max_display} more")


def display_sample_urls(urls: List[str]):
    """Display selected sample URLs"""
    print(f"📌 Sample URLs ({len(urls)}):")
    for i, url in enumerate(urls, 1):
        # Truncate long URLs for display
        display_url = url if len(url) <= 80 else url[:77] + "..."
        print(f"  [{i}] {display_url}")


def display_article_extraction(extraction: Dict[str, Any], url: str):
    """Display article extraction results"""
    print(f"🧪 Testing article schema on: {url[:80]}...")
    
    if not extraction:
        print("❌ No extraction results")
        return
    
    print("📄 Extracted:")
    
    # Display common fields
    for field_name in ['title', 'author', 'date', 'content']:
        if field_name in extraction:
            value = extraction[field_name]
            if value:
                # Truncate long content
                if field_name == 'content' and len(str(value)) > 200:
                    display_value = str(value)[:197] + "..."
                else:
                    display_value = str(value)
                print(f"  {field_name.title()}: \"{display_value}\"")
            else:
                print(f"  {field_name.title()}: (empty)")
    
    # Display any other fields
    other_fields = [k for k in extraction.keys() if k not in ['title', 'author', 'date', 'content']]
    for field_name in other_fields:
        value = extraction[field_name]
        if value:
            if len(str(value)) > 100:
                display_value = str(value)[:97] + "..."
            else:
                display_value = str(value)
            print(f"  {field_name}: \"{display_value}\"")


def display_article_extraction_full(extraction: Dict[str, Any], url: str, exclude_field: str = None):
    """Display article extraction results with FULL field details (no truncation)"""
    print(f"🧪 Testing article schema on: {url}")
    if exclude_field:
        print(f"🚫 Excluding field: {exclude_field}")
    print("=" * 80)
    
    if not extraction:
        print("❌ No extraction results")
        return
    
    print("📄 EXTRACTED CONTENT (FULL):")
    print()
    
    # Display all fields with full content (except excluded field)
    for field_name, value in extraction.items():
        if exclude_field and field_name.lower() == exclude_field.lower():
            continue  # Skip excluded field
            
        if value:
            print(f"🔹 {field_name.upper()}:")
            print(f"   {str(value)}")
            print()
        else:
            print(f"🔹 {field_name.upper()}: (empty)")
            print()
    
    print("=" * 80)


def display_validation_results(comparisons: List[Dict], overall_score: float):
    """Display validation results"""
    print(f"📊 Running full validation on {len(comparisons)} sample URLs...")
    
    for i, comparison in enumerate(comparisons, 1):
        score = comparison.get('completeness_score', 0)
        status = "✅" if score >= 80 else "⚠️" if score >= 60 else "❌"
        print(f"  [{i}] {status} {score:.1f}% - {comparison.get('url', 'Unknown URL')[:60]}...")
        
        # Show specific issues if any
        missing = comparison.get('missing_content', [])
        if missing:
            print(f"      Missing: {', '.join(missing[:3])}")
    
    print(f"\n📈 Overall score: {overall_score:.1f}%")
    
    if overall_score >= 90:
        print("✅ Schema ready for production use!")
    elif overall_score >= 80:
        print("⚠️ Schema is good but could be improved")
    else:
        print("❌ Schema needs improvement - try using 'improve' command")


def display_schema_info(schema: Dict[str, Any], schema_type: str = "schema"):
    """Display schema information"""
    if not schema:
        print(f"❌ No {schema_type} available")
        return
    
    name = schema.get('name', 'Unknown')
    base_selector = schema.get('baseSelector', 'N/A')
    fields = schema.get('fields', [])
    
    print(f"📋 {schema_type.title()} Info:")
    print(f"  Name: {name}")
    print(f"  Base Selector: {base_selector}")
    print(f"  Fields: {len(fields)}")
    
    # Show first few fields
    for i, field in enumerate(fields[:3]):
        field_name = field.get('name', 'unnamed')
        field_type = field.get('type', 'unknown')
        print(f"    • {field_name} ({field_type})")
    
    if len(fields) > 3:
        print(f"    ... and {len(fields) - 3} more fields")


def display_error(message: str):
    """Display error message"""
    print(f"❌ {message}")


def display_success(message: str):
    """Display success message"""
    print(f"✅ {message}")


def display_info(message: str):
    """Display info message"""
    print(f"ℹ️ {message}")


def display_working_on(source_name: str, url: str):
    """Display current working source"""
    print(f"✅ Now working with: {source_name} ({url})")


def truncate_url(url: str, max_length: int = 80) -> str:
    """Truncate URL for display"""
    if len(url) <= max_length:
        return url
    return url[:max_length-3] + "..."


# New display functions for CRUD operations
def display_articles_list(urls: List[str]):
    """Display the list of sample URLs with IDs"""
    if not urls:
        print("📋 No sample URLs attached")
        return
    
    print(f"📋 Sample URLs ({len(urls)}):")
    for i, url in enumerate(urls, 1):
        # Truncate long URLs for display
        display_url = url if len(url) <= 80 else url[:77] + "..."
        print(f"  [{i}] {display_url}")


def display_schema_test_results(results: List[Dict[str, Any]], urls: List[str]):
    """Display results from testing schema on multiple URLs"""
    print(f"🧪 Schema test results for {len(results)} URLs:")
    print("=" * 80)
    
    for i, (result, url) in enumerate(zip(results, urls), 1):
        print(f"📄 URL {i}: {url}")
        print(f"   Status: {'✅ Success' if result else '❌ Failed'}")
        
        if result:
            # Show field summary
            fields_with_content = [k for k, v in result.items() if v]
            print(f"   Fields extracted: {len(fields_with_content)}/{len(result)}")
            print(f"   Fields: {', '.join(fields_with_content)}")
        else:
            print("   No content extracted")
        
        print()
    
    print("=" * 80) 