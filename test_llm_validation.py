#!/usr/bin/env python3
"""
Simple test to verify LLM ground truth validation is working
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

async def test_llm_validation():
    """Test the LLM ground truth validation system"""
    print("🧪 Testing LLM Ground Truth Validation...")
    
    try:
        from tools.article_schema_generator import generate_validated_article_schema
        
        # Use a simple source with 2 test URLs
        base_url = "https://techcrunch.com"
        sample_urls = [
            "https://techcrunch.com/2025/01/20/trump-executive-orders-ai/",
            "https://techcrunch.com/2025/01/19/google-deepmind-model/"
        ]
        
        print(f"Testing schema generation for: {base_url}")
        print(f"Sample URLs: {len(sample_urls)} URLs")
        
        # This should use the restored LLM ground truth validation
        result = await generate_validated_article_schema(base_url, sample_urls)
        
        print(f"\n✅ Schema generation completed!")
        print(f"Result length: {len(result)} characters")
        
        # Check for the right validation method
        if "ground truth" in result.lower():
            print("✅ Using LLM ground truth validation")
        elif "objective" in result.lower():
            print("❌ Still using objective validation")
        else:
            print("⚠️ Validation method unclear")
        
        # Look for validation scores
        if "validation_score" in result:
            print("✅ Validation scores included")
        
        print(f"\nFirst 300 chars: {result[:300]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(test_llm_validation()) 