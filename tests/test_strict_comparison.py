#!/usr/bin/env python3

import asyncio
import os
import json
from pathlib import Path
import sys

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

async def test_strict_comparison():
    """Test the new strict comparison logic"""
    print("🧪 Testing strict comparison logic...")
    
    try:
        from tools.article_schema_generator import compare_article_extractions
        
        # Test 1: Perfect match (should score ~100%)
        print("\n🎯 Test 1: Perfect match")
        schema_result = {
            'title': 'Apple Announces New iPhone',
            'author': 'John Smith',
            'date_published': '2025-06-20T10:00:00Z',
            'content': [
                {'text': 'This is the complete article about Apple\'s new iPhone announcement.'},
                {'text': 'The device features revolutionary AI capabilities.'},
                {'text': 'It will be available starting next month for $999.'}
            ]
        }
        
        ground_truth = {
            'title': 'Apple Announces New iPhone',
            'author': 'John Smith', 
            'date_published': '2025-06-20T10:00:00Z',
            'content': 'This is the complete article about Apple\'s new iPhone announcement. The device features revolutionary AI capabilities. It will be available starting next month for $999.'
        }
        
        result = await compare_article_extractions(schema_result, ground_truth, "test-url-1")
        print(f"   ✅ Perfect match score: {result['score']:.1f}% (expected: ~95-100%)")
        
        # Test 2: Missing title (should fail)
        print("\n🎯 Test 2: Missing title (should fail)")
        schema_result_no_title = {
            'title': '',
            'author': 'John Smith',
            'date_published': '2025-06-20T10:00:00Z',
            'content': [{'text': 'Article content here with sufficient length to pass the minimum 100 character requirement for meaningful content validation. This ensures we test only the title validation.'}]
        }
        
        result = await compare_article_extractions(schema_result_no_title, ground_truth, "test-url-2")
        print(f"   ❌ Missing title score: {result['score']:.1f}% (expected: 0%)")
        print(f"   📋 Issues: {result.get('issues', [])}")
        
        # Test 3: LLM ground truth failure (should fail)
        print("\n🎯 Test 3: LLM ground truth failure (should fail)")
        failed_ground_truth = {
            'title': 'NO_TITLE_EXTRACTED',
            'author': '',
            'date_published': '',
            'content': "'str' object has no attribute 'choices'"
        }
        
        result = await compare_article_extractions(schema_result, failed_ground_truth, "test-url-3")
        print(f"   ❌ LLM failure score: {result['score']:.1f}% (expected: 0%)")
        print(f"   📋 Issues: {result.get('issues', [])}")
        
        # Test 4: Partial match (should score moderately)
        print("\n🎯 Test 4: Partial match (should score moderately)")
        schema_result_partial = {
            'title': 'Apple Announces New iPhone Pro',
            'author': 'John Smith',
            'date_published': '2025-06-20',
            'content': [
                {'text': 'This article discusses Apple\'s latest iPhone announcement with comprehensive details about the new features.'},
                {'text': 'The new device has many improvements including better battery life, enhanced cameras, and faster processing.'},
                {'text': 'Apple expects this to be their most successful product launch in recent years.'}
            ]
        }
        
        result = await compare_article_extractions(schema_result_partial, ground_truth, "test-url-4")
        print(f"   🟡 Partial match score: {result['score']:.1f}% (expected: 50-80%)")
        if 'scores' in result:
            for field, data in result['scores'].items():
                print(f"      {field}: {data['similarity']:.2f} → {data['score']:.1f}/{data['weight']}")
        
        # Test 5: Missing date (should fail)
        print("\n🎯 Test 5: Missing date (should fail)")
        schema_result_no_date = {
            'title': 'Apple Announces New iPhone',
            'author': 'John Smith',
            'date_published': '',
            'content': [{'text': 'Article content here with enough text to pass length requirements...'}]
        }
        
        result = await compare_article_extractions(schema_result_no_date, ground_truth, "test-url-5")
        print(f"   ❌ Missing date score: {result['score']:.1f}% (expected: 0%)")
        print(f"   📋 Issues: {result.get('issues', [])}")
        
        print("\n✅ Strict comparison testing completed!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(test_strict_comparison()) 