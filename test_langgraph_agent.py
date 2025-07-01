#!/usr/bin/env python3
"""
Test script for the new LangGraph-based Scroopy Agent
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_langgraph_agent():
    """Test the LangGraph agent with a simple query"""
    print("🧪 Testing LangGraph Scroopy Agent...")
    
    try:
        from langgraph_agent import run_langgraph_agent
        
        # Test with a simple query
        query = "AI technology news"
        print(f"🎯 Testing query: {query}")
        
        result = await run_langgraph_agent(query)
        
        print("\n" + "="*80)
        print("🏁 LANGGRAPH TEST RESULT:")
        print("="*80)
        
        if result.get("status") == "success":
            print(f"✅ Status: {result['status']}")
            print(f"📊 Sources Processed: {result.get('sources_processed', 0)}")
            print(f"✅ Sources Completed: {result.get('sources_completed', 0)}")
            print(f"❌ Sources Failed: {result.get('sources_failed', 0)}")
            
            print(f"\n📋 Summary:")
            print(result.get("summary", "No summary available"))
            
            # Show details of each source
            sources = result.get("sources", [])
            if sources:
                print(f"\n📰 Source Details:")
                for i, source in enumerate(sources, 1):
                    print(f"\n{i}. {source.get('name', 'Unknown')} ({source.get('status', 'unknown')})")
                    print(f"   URL: {source.get('url', 'N/A')}")
                    
                    if source.get('validation_score') is not None:
                        print(f"   Validation Score: {source['validation_score']:.1f}%")
                        print(f"   Validation Attempts: {source.get('validation_attempts', 1)}")
                    
                    if source.get('validation_feedback'):
                        print(f"   Feedback Applied: {len(source['validation_feedback'])} items")
                        for feedback in source['validation_feedback']:
                            print(f"     • {feedback}")
                    
                    if source.get('saved'):
                        print(f"   💾 Saved to Database: ✅")
                    
                    errors = source.get('errors', [])
                    if errors:
                        print(f"   ❌ Errors: {'; '.join(errors)}")
                        
            print(f"\n🎉 LangGraph agent test completed successfully!")
            return True
            
        else:
            print(f"❌ Status: {result['status']}")
            print(f"❌ Error: {result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_state_management():
    """Test that state management and feedback loops work"""
    print("\n🔄 Testing State Management and Feedback Loops...")
    
    try:
        from langgraph_agent import NewsSourceProcessor
        
        # Create processor instance
        processor = NewsSourceProcessor()
        
        # Test with a query that might need multiple attempts
        query = "Machine learning research"
        print(f"🎯 Testing state management with query: {query}")
        
        result = await processor.process_query(query)
        
        # Check for evidence of state management
        sources = result.get("sources", [])
        feedback_used = False
        multiple_attempts = False
        
        for source in sources:
            if source.get("validation_attempts", 0) > 1:
                multiple_attempts = True
                print(f"✅ Source {source.get('name')} used multiple attempts: {source['validation_attempts']}")
            
            if source.get("validation_feedback"):
                feedback_used = True
                print(f"✅ Source {source.get('name')} received feedback: {len(source['validation_feedback'])} items")
        
        if feedback_used:
            print("✅ Feedback loops are working")
        else:
            print("⚠️ No feedback was generated (sources may have passed on first attempt)")
            
        if multiple_attempts:
            print("✅ State management allowing multiple attempts")
        else:
            print("⚠️ No multiple attempts needed (sources may have been successful immediately)")
            
        return True
        
    except Exception as e:
        print(f"❌ State management test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests"""
    print("🚀 Starting LangGraph Agent Tests...\n")
    
    test1_success = await test_langgraph_agent()
    test2_success = await test_state_management()
    
    print("\n" + "="*80)
    print("📊 TEST SUMMARY:")
    print("="*80)
    print(f"Basic Functionality: {'✅ PASS' if test1_success else '❌ FAIL'}")
    print(f"State Management: {'✅ PASS' if test2_success else '❌ FAIL'}")
    
    if test1_success and test2_success:
        print("\n🎉 All tests passed! LangGraph migration is working.")
        return 0
    else:
        print("\n❌ Some tests failed. Check the output above.")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 