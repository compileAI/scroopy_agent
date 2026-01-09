#!/usr/bin/env python3
"""
Test script to verify Supabase cache implementation

Usage:
    python test_cache_migration.py

This script tests:
1. Connection to Supabase
2. Basic cache operations (set, get, delete)
3. Different data types (string, object, array)
4. Cache key parsing
"""

import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from utils.stagehand_cache import (
    get_cache,
    set_cache,
    clear_cache_key,
    url_hash,
    content_hash,
    _parse_cache_type
)

# Load environment variables
load_dotenv()


async def test_connection():
    """Test 1: Verify Supabase connection"""
    print("\n🔌 Test 1: Supabase Connection")
    print("-" * 50)
    
    try:
        from utils.stagehand_cache import get_cache_client
        client = get_cache_client()
        
        # Try a simple query
        result = client.table('stagehand_cache').select('key', count='exact').limit(1).execute()
        print(f"✅ Connected to Supabase")
        print(f"   stagehand_cache table has {result.count} entries")
        return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


async def test_string_cache():
    """Test 2: String cache operations"""
    print("\n📝 Test 2: String Cache Operations")
    print("-" * 50)
    
    test_key = "test_string_key"
    test_value = "Hello, Supabase!"
    
    try:
        # Set
        print(f"   Setting key '{test_key}' = '{test_value}'")
        await set_cache(test_key, test_value)
        
        # Get
        result = await get_cache(test_key)
        print(f"   Retrieved: '{result}'")
        
        assert result == test_value, f"Expected '{test_value}', got '{result}'"
        
        # Clear
        await clear_cache_key(test_key)
        cleared = await get_cache(test_key)
        assert cleared is None, f"Key should be deleted, got: {cleared}"
        
        print("✅ String cache operations work correctly")
        return True
    
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


async def test_object_cache():
    """Test 3: Object cache operations"""
    print("\n📦 Test 3: Object Cache Operations")
    print("-" * 50)
    
    test_key = "test_object_key"
    test_value = {
        "title": "Test Article",
        "author": "Test Author",
        "content": ["Paragraph 1", "Paragraph 2"]
    }
    
    try:
        # Set
        print(f"   Setting object with keys: {list(test_value.keys())}")
        await set_cache(test_key, test_value)
        
        # Get
        result = await get_cache(test_key)
        print(f"   Retrieved object with keys: {list(result.keys())}")
        
        assert result == test_value, f"Object mismatch"
        assert result["title"] == "Test Article"
        assert len(result["content"]) == 2
        
        # Clear
        await clear_cache_key(test_key)
        
        print("✅ Object cache operations work correctly")
        return True
    
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


async def test_dom_hash_scenario():
    """Test 4: Realistic DOM hash scenario"""
    print("\n🌐 Test 4: DOM Hash Scenario")
    print("-" * 50)
    
    test_url = "https://example.com/blog/article"
    test_content = "<html><body>Article content here</body></html>"
    
    try:
        # Generate hashes like the real code does
        url_key = url_hash(test_url)
        dom_hash_key = f"dom_hash_{url_key}"
        current_hash = content_hash(test_content)
        
        print(f"   URL: {test_url}")
        print(f"   URL Hash: {url_key}")
        print(f"   DOM Hash Key: {dom_hash_key}")
        print(f"   Content Hash: {current_hash}")
        
        # Cache the DOM hash
        await set_cache(dom_hash_key, current_hash)
        
        # Retrieve and verify
        cached_hash = await get_cache(dom_hash_key)
        assert cached_hash == current_hash, "DOM hash mismatch"
        
        # Verify cache type parsing
        cache_type, extracted_url_hash = _parse_cache_type(dom_hash_key)
        assert cache_type == "dom_hash", f"Expected 'dom_hash', got '{cache_type}'"
        assert extracted_url_hash == url_key, "URL hash mismatch"
        
        # Clean up
        await clear_cache_key(dom_hash_key)
        
        print("✅ DOM hash scenario works correctly")
        return True
    
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


async def test_article_extraction_scenario():
    """Test 5: Realistic article extraction scenario"""
    print("\n📰 Test 5: Article Extraction Scenario")
    print("-" * 50)
    
    test_url = "https://example.com/blog/test-article"
    article_data = {
        "title": "Test Article Title",
        "author": "John Doe",
        "date_published": "2025-12-22",
        "content": [
            "First paragraph of the article.",
            "Second paragraph with more content.",
            "Third paragraph concluding the article."
        ]
    }
    
    try:
        url_key = url_hash(test_url)
        cache_key = f"article_extraction_{url_key}"
        
        print(f"   URL: {test_url}")
        print(f"   Cache Key: {cache_key}")
        print(f"   Article: {article_data['title']}")
        
        # Cache the article
        await set_cache(cache_key, article_data)
        
        # Retrieve and verify
        cached_article = await get_cache(cache_key)
        assert cached_article is not None, "Article not found in cache"
        assert cached_article["title"] == article_data["title"]
        assert len(cached_article["content"]) == 3
        
        # Verify cache type
        cache_type, _ = _parse_cache_type(cache_key)
        assert cache_type == "article_extraction"
        
        # Clean up
        await clear_cache_key(cache_key)
        
        print("✅ Article extraction scenario works correctly")
        return True
    
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


async def main():
    """Run all tests"""
    print("=" * 50)
    print("🧪 Supabase Cache Implementation Tests")
    print("=" * 50)
    
    tests = [
        ("Connection", test_connection),
        ("String Cache", test_string_cache),
        ("Object Cache", test_object_cache),
        ("DOM Hash", test_dom_hash_scenario),
        ("Article Extraction", test_article_extraction_scenario)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        result = await test_func()
        results.append((test_name, result))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Summary")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print("\n" + "-" * 50)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

