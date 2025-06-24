#!/usr/bin/env python3

import asyncio
import os
import json
from pathlib import Path
import sys

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

async def test_comparison_fix():
    """Test the specific fix for the 'choices' attribute error in comparison"""
    print("🧪 Testing LLM comparison fix...")
    
    try:
        from tools.article_schema_generator import compare_article_extractions
        
        # Create sample data that would trigger the comparison
        schema_result = {
            'title': 'Test Article Title',
            'content': [
                {'text': 'This is the first paragraph of the test article.'},
                {'text': 'This is the second paragraph with more content.'}
            ],
            'author': 'Test Author',
            'date_published': '2024-01-01'
        }
        
        llm_result = {
            'title': 'Test Article Title',
            'content': 'This is the first paragraph of the test article. This is the second paragraph with more content.',
            'author': 'Test Author',
            'date_published': '2024-01-01'
        }
        
        print(f"📊 Testing comparison with sample data...")
        
        # This should no longer cause the 'choices' attribute error
        result = await compare_article_extractions(schema_result, llm_result, 1)
        
        print(f"✅ Comparison completed successfully!")
        print(f"📋 Result type: {type(result)}")
        print(f"📋 Result keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
        
        if isinstance(result, dict):
            score = result.get('completeness_score', 0)
            print(f"📊 Comparison score: {score}%")
            return True
        else:
            print(f"❌ Unexpected result format")
            return False
        
    except Exception as e:
        print(f"❌ Comparison test failed: {e}")
        # Check if this is the specific error we're trying to fix
        if "'str' object has no attribute 'choices'" in str(e):
            print(f"   🎯 The 'choices' error still exists!")
        import traceback
        traceback.print_exc()
        return False

async def test_ground_truth_extraction():
    """Test ground truth extraction specifically"""
    print("\n🧪 Testing ground truth extraction...")
    
    try:
        from tools.article_schema_generator import extract_article_with_llm
        
        # Use a simple, reliable news URL
        test_url = "https://www.bbc.com/news"
        
        print(f"🔍 Testing extraction on: {test_url}")
        
        result = await extract_article_with_llm(test_url)
        
        if result is None:
            print(f"   ❌ Extraction returned None")
            return False
        
        print(f"✅ Extraction completed!")
        print(f"📋 Result type: {type(result)}")
        
        if isinstance(result, dict):
            title = result.get('title', 'MISSING')
            content = result.get('content', 'MISSING')
            
            print(f"   Title: {title}")
            print(f"   Content length: {len(content) if content != 'MISSING' else 0}")
            print(f"   Content preview: {content[:100] if content != 'MISSING' else 'NONE'}...")
            
            # Check for the specific error we saw
            if title == "NO_TITLE_EXTRACTED":
                print(f"   ⚠️ Found NO_TITLE_EXTRACTED issue")
                if "'str' object has no attribute 'choices'" in content:
                    print(f"   🎯 Found the 'choices' error in content!")
                    return False
            
            return True
        else:
            print(f"   ❌ Unexpected result type: {type(result)}")
            return False
        
    except Exception as e:
        print(f"❌ Ground truth extraction test failed: {e}")
        if "'str' object has no attribute 'choices'" in str(e):
            print(f"   🎯 The 'choices' error occurred during extraction!")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    async def run_specific_tests():
        print("🎯 SPECIFIC FIX TESTS")
        print("="*50)
        
        # Test 1: Comparison fix
        success1 = await test_comparison_fix()
        
        # Test 2: Ground truth extraction
        success2 = await test_ground_truth_extraction()
        
        print("\n" + "="*50)
        print("🏁 SPECIFIC TEST RESULTS")
        print("="*50)
        print(f"Comparison fix: {'✅ PASS' if success1 else '❌ FAIL'}")
        print(f"Ground truth extraction: {'✅ PASS' if success2 else '❌ FAIL'}")
        
        overall_success = success1 and success2
        print(f"\nOverall: {'🎉 FIXES WORKING' if overall_success else '🔧 ISSUES REMAIN'}")
    
    asyncio.run(run_specific_tests()) 