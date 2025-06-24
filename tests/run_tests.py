#!/usr/bin/env python3
"""
Test runner for Scroopy Agent
Runs all diagnostic tests to identify and fix issues
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)
    print(f"✅ Environment loaded from {env_path}")
except ImportError:
    print("⚠️ python-dotenv not installed")

async def run_crawler_tests():
    """Run crawler-related tests"""
    print("="*80)
    print("🕷️ CRAWLER TESTS")
    print("="*80)
    
    try:
        from test_crawler_cleanup import test_crawler_methods, test_environment
        await test_crawler_methods()
        await test_environment()
    except Exception as e:
        print(f"❌ Crawler tests failed: {e}")

async def run_llm_tests():
    """Run LLM-related tests"""
    print("\n" + "="*80)
    print("🤖 LLM TESTS")  
    print("="*80)
    
    try:
        from test_llm_ground_truth import test_llm_config, test_simple_llm_call, test_discovery_function, test_crawl4ai_llm_extraction
        
        config = await test_llm_config()
        if config:
            await test_simple_llm_call()
            await test_discovery_function()
            await test_crawl4ai_llm_extraction()
        else:
            print("❌ Cannot run LLM tests without configuration")
    except Exception as e:
        print(f"❌ LLM tests failed: {e}")

async def run_integration_test():
    """Run a small integration test"""
    print("\n" + "="*80)
    print("🔧 INTEGRATION TEST")
    print("="*80)
    
    try:
        from structured_agent import run_structured_agent
        
        print("🧪 Running mini integration test...")
        result = await run_structured_agent("AI research")
        
        print(f"📊 Integration test result:")
        print(f"   Status: {result.get('status', 'MISSING')}")
        print(f"   Sources processed: {result.get('sources_processed', 0)}")
        
        if result.get('status') == 'success':
            print("   ✅ Integration test passed")
        else:
            print(f"   ❌ Integration test failed: {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """Run all tests"""
    print("🧪 SCROOPY AGENT DIAGNOSTIC TESTS")
    print("🔍 Identifying and fixing issues systematically")
    print("⏰ Started at:", asyncio.get_event_loop().time())
    
    # Run tests in order
    await run_crawler_tests()
    await run_llm_tests()
    await run_integration_test()
    
    print("\n" + "="*80)
    print("🏁 TESTS COMPLETED")
    print("="*80)
    print("📝 Review the output above to identify issues")
    print("🔧 Apply fixes based on the test results")

if __name__ == "__main__":
    asyncio.run(main()) 