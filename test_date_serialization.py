#!/usr/bin/env python3
"""
Test to verify Article date serialization works correctly with JSON mode.

This test ensures that Article.model_dump(mode='json') properly serializes
date objects to strings, making them JSON-serializable.
"""

import json
import sys
from pathlib import Path
from datetime import date

# Add src to path
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from models.stagehand import Article


def test_model_dump_json_mode():
    """Test that model_dump(mode='json') serializes dates to strings"""
    print("\n🧪 Test: Article.model_dump(mode='json') date serialization")
    print("-" * 60)
    
    # Create an Article with a string date (validator converts it to date object)
    test_date_str = "2025-12-22"
    article = Article(
        title="Test Article",
        author="John Doe",
        date_published=test_date_str,
        content=["First paragraph", "Second paragraph"]
    )
    
    # Get the parsed date object
    test_date = article.date_published
    
    print(f"   Created article with date: {test_date} (type: {type(test_date).__name__})")
    
    # Test model_dump() - should have date object
    dump_result = article.model_dump()
    print(f"\n   model_dump() result:")
    print(f"     date_published: {dump_result['date_published']} (type: {type(dump_result['date_published']).__name__})")
    
    # Verify it's a date object (not JSON serializable)
    assert isinstance(dump_result['date_published'], date), "Should be a date object"
    
    # Test that it's NOT JSON serializable
    try:
        json.dumps(dump_result)
        print("   ❌ ERROR: model_dump() result is JSON serializable (should not be!)")
        return False
    except TypeError as e:
        print(f"   ✅ Correctly failed JSON serialization: {type(e).__name__}")
    
    # Test model_dump(mode='json') - should have date as string
    json_result = article.model_dump(mode='json')
    print(f"\n   model_dump(mode='json') result:")
    print(f"     date_published: {json_result['date_published']} (type: {type(json_result['date_published']).__name__})")
    
    # Verify it's a string
    assert isinstance(json_result['date_published'], str), "Should be a string in JSON mode"
    assert json_result['date_published'] == "2025-12-22", "Should be ISO format string"
    
    # Test that it IS JSON serializable
    try:
        json_str = json.dumps(json_result)
        print(f"   ✅ Successfully serialized to JSON")
        
        # Test deserialization
        deserialized = json.loads(json_str)
        assert deserialized['date_published'] == "2025-12-22"
        print(f"   ✅ Successfully deserialized from JSON")
        
        # Test that we can reconstruct Article from JSON mode dump
        article_from_json = Article(**json_result)
        assert article_from_json.date_published == test_date, f"Expected {test_date}, got {article_from_json.date_published}"
        print(f"   ✅ Successfully reconstructed Article from JSON mode dump")
        
        return True
    except Exception as e:
        print(f"   ❌ Failed JSON serialization: {e}")
        return False


def test_stagehand_extraction_simulation():
    """Test that simulates the actual Stagehand extraction flow"""
    print("\n🧪 Test: Simulating Stagehand extraction flow")
    print("-" * 60)
    
    try:
        # Simulate what Stagehand's page.extract() would return
        # Stagehand returns a dict with string dates (as per instruction "ISO publication date (YYYY-MM-DD)")
        stagehand_result = {
            "title": "Test Article from Stagehand",
            "author": "Jane Doe",
            "date_published": "2025-12-22",  # Stagehand returns string (ISO format)
            "content": ["First paragraph", "Second paragraph"]
        }
        
        print(f"   Stagehand returns: date_published='{stagehand_result['date_published']}' (type: {type(stagehand_result['date_published']).__name__})")
        
        # This is what happens in extract_article_with_cache line 341:
        # article = rec if isinstance(rec, Article) else Article(**rec)
        article = Article(**stagehand_result)
        
        # At this point, the validator has converted the string to a date object
        assert isinstance(article.date_published, date), "Validator should convert string to date object"
        print(f"   After Article(**rec): date_published={article.date_published} (type: {type(article.date_published).__name__})")
        
        # This is what happens in extract_article_with_cache line 350:
        # await set_cache(cache_key, article.model_dump(mode='json'))
        article_dict = article.model_dump(mode='json')
        
        # Verify it's JSON serializable (this is what was failing before the fix)
        json_str = json.dumps(article_dict)
        assert isinstance(article_dict['date_published'], str), "Should be string after model_dump(mode='json')"
        assert article_dict['date_published'] == "2025-12-22", "Should be ISO format string"
        print(f"   After model_dump(mode='json'): date_published='{article_dict['date_published']}' (type: {type(article_dict['date_published']).__name__})")
        print("   ✅ Successfully serialized to JSON (this would work with set_cache)")
        
        # Test reading from cache (line 324): Article(**cached_result)
        cached_result = json.loads(json_str)  # Simulate what get_cache would return
        article_from_cache = Article(**cached_result)
        assert isinstance(article_from_cache.date_published, date), "Should be date object after reconstructing from cache"
        assert article_from_cache.date_published == article.date_published, "Should match original date"
        print(f"   After reading from cache: date_published={article_from_cache.date_published} (type: {type(article_from_cache.date_published).__name__})")
        print("   ✅ Successfully reconstructed Article from cached JSON")
        
        return True
    except Exception as e:
        print(f"   ❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_set_cache_compatibility():
    """Test that model_dump(mode='json') works with set_cache"""
    print("\n🧪 Test: Compatibility with set_cache function")
    print("-" * 60)
    
    try:
        from utils.stagehand_cache import set_cache
        
        # Create an Article with a string date (validator converts it to date object)
        article = Article(
            title="Test Article for Cache",
            author="Jane Doe",
            date_published="2025-12-22",
            content=["Content paragraph"]
        )
        
        # Use model_dump(mode='json') as in the fixed code
        article_dict = article.model_dump(mode='json')
        
        # Verify it's JSON serializable before trying to cache
        json.dumps(article_dict)
        print("   ✅ article.model_dump(mode='json') is JSON serializable")
        
        # Test that set_cache can handle it (it will try to serialize it)
        # We can't actually test the full set_cache without Supabase, but we can
        # verify the data is in the right format
        assert isinstance(article_dict['date_published'], str)
        assert article_dict['date_published'] == "2025-12-22"
        print("   ✅ Date is properly serialized as string for cache")
        
        return True
    except Exception as e:
        print(f"   ❌ Test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("🧪 Article Date Serialization Tests")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("model_dump(mode='json') serialization", test_model_dump_json_mode()))
    results.append(("Stagehand extraction simulation", test_stagehand_extraction_simulation()))
    results.append(("set_cache compatibility", test_set_cache_compatibility()))
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    
    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("✅ All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
